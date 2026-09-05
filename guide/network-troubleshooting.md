# HTTP、TCP、TLS 与网络排障

后端排障先回答三个问题：请求有没有到达、连接在哪一步失败、服务是否已经执行。不要把所有错误都归因于“接口慢”。

## 一次请求经过什么

```txt
DNS → TCP 三次握手 → TLS 握手 → HTTP 请求/响应 → 连接复用或关闭
```

DNS 失败通常没有连接；TCP 连接失败说明端口、路由或防火墙问题；TLS 失败要看证书、SNI、协议和 ALPN；HTTP 4xx/5xx 则说明请求已经到达某个 HTTP 服务。

## 用 curl 拆时间

```bash
curl -sS -o /dev/null -w 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' https://example.com/health
```

这是观测单次请求的线索，不是完整分布式追踪。`connect` 包含 TCP 建连，`time_appconnect` 反映 TLS 完成；复用连接时这些值可能接近零。对比域名、IP、代理和容器内外结果，先定位作用域再改配置。

## HTTP 语义决定能否重试

连接超时不代表服务没有执行：请求可能已经到达并完成写库，只是响应丢失。GET、HEAD 等幂等请求通常更容易安全重试；POST 要使用幂等键或业务去重。重试必须有超时、次数上限、退避和总预算，否则会把下游故障放大。

看到 502 要继续区分：网关无法连接上游、上游提前断开、响应头超时、响应体读取超时。分别检查网关错误日志、上游监听地址、连接池和应用 request id。

## TLS 快速核对

```bash
curl -vkI https://api.example.com/health
openssl s_client -connect api.example.com:443 -servername api.example.com -alpn h2
```

`-k` 只用于本地观察握手，不能作为修复方案。证书的 SAN 必须匹配域名；多站点 HTTPS 依赖 SNI；HTTP/2 协商依赖 ALPN。证书过期、链不完整、系统时钟错误都可能表现为“HTTPS 连不上”。

## 排障顺序

1. 记录时间、请求 ID、客户端与服务端地址。
2. 从客户端、网关、容器、应用日志对齐同一请求。
3. 用 `getent hosts`、`ss -lntp`、`curl -v` 证明 DNS、监听和协议状态。
4. 检查连接池、文件描述符、线程/协程池和下游超时。
5. 修复后重复同一条探针，并确认业务副作用没有重复发生。

不要默认执行 `kill -9` 或重启；先保留日志、堆栈和连接状态。生产命令需按权限、变更流程和回滚方案执行。

## 面试怎么说

> 我先把请求拆成 DNS、TCP、TLS、HTTP 四段，用时间数据和 request id 定位边界。超时不等于未执行，所以写操作重试前要有幂等键。502 要区分网关到不了上游、上游主动断开和响应超时，再分别查网络、进程和下游依赖。

## 练习

本地起一个 HTTP 服务，分别制造 DNS 错误、未监听端口、延迟响应和 500；用 `curl -v` 与 `-w` 记录差异。练习只使用本机地址，不对生产服务发压测。

## 参考

- [curl write-out](https://curl.se/docs/manpage.html#-w)
- [MDN HTTP 状态码](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Status)
- [OpenSSL s_client](https://docs.openssl.org/3.0/man1/openssl-s_client/)

## DNS：先确认解析结果，再谈应用

```bash
getent ahosts api.example.com
# 容器内执行，比较宿主机结果
cat /etc/resolv.conf
```

同一域名可能返回多个地址（轮询、IPv4/IPv6、地域 DNS）。`getent` 证明的是当前解析器给出的结果，不证明每个地址都可达。关注 TTL、搜索域、容器 DNS 和是否存在 AAAA 记录导致客户端优先尝试 IPv6。不要直接把 `/etc/hosts` 当生产修复；它会绕过 DNS 变更并制造漂移。

## TCP：连接成功不等于请求成功

三次握手建立连接，四次挥手关闭连接；RST 表示连接被异常重置。排查监听和连接状态：

```bash
ss -lntp                 # 谁在监听 TCP 端口
ss -ant state syn-recv  # 是否堆积半连接
ss -ant state time-wait | wc -l
```

`SYN-RECV` 多且持续增长，优先查服务 accept、网络策略和 backlog；`TIME-WAIT` 是主动关闭方的正常状态，不能仅凭数量下结论。容器中 `127.0.0.1` 只代表容器自身，服务间访问应使用监听的 `0.0.0.0` 与服务名。

## TLS 与 HTTP 版本

HTTP/1.1 常用一个连接顺序处理请求，队头阻塞会放大慢请求；HTTP/2 在一条 TCP 连接上多路复用，但 TCP 丢包仍会影响整条连接；HTTP/3 基于 QUIC/UDP，是否可用由客户端、网关和负载均衡共同决定。不要把“启用 HTTP/2”当作单纯改应用代码。

```bash
curl -v --http1.1 https://api.example.com/health
curl -v --http2   https://api.example.com/health
```

看输出中的 `ALPN: server accepted`、协议版本和响应头，确认协商结果。代理可能在客户端到网关使用 HTTP/2、网关到上游仍使用 HTTP/1.1，因此要分别测两段。

## 超时必须形成预算

一次请求通常包含连接超时、TLS 超时、响应头超时、响应体读取超时和总截止时间。下游调用的总预算必须小于上游剩余预算，否则上游已经超时，后台调用还会继续占用连接和线程。

```txt
入口总截止时间 2s
  ├─ DNS/TCP/TLS 300ms
  ├─ 下游 A 800ms（含最多一次重试）
  └─ 数据库 600ms
```

超时后要取消下游请求并释放连接；只在调用方返回 504、却让下游继续跑，会造成“幽灵请求”。日志至少记录 timeout 类型、耗时、attempt、上游地址和 request id。

## 502、503、504 怎么拆

| 状态 | 典型边界 | 首先查什么 |
|---|---|---|
| 502 | 网关拿到无效响应、连接被上游重置 | 网关 error log、上游进程日志、协议/端口 |
| 503 | 当前服务不可用或没有健康实例 | readiness、连接池、限流和负载均衡成员 |
| 504 | 网关等待上游超时 | 上游耗时分位数、下游依赖、网关 timeout 配置 |

状态码只是观测点。应用也可能自己返回 502；必须结合 `Server`、网关 request id 和应用日志确认产生者。

## 连接池与资源耗尽

HTTP keep-alive、数据库连接池和文件描述符都属于有限资源。连接池过小会排队，过大则把压力推给下游；必须同时观察 active、idle、pending、获取连接耗时。`ulimit -n` 只是上限，不能替代应用指标。

```bash
lsof -p <pid> | wc -l
# 仅查看自己启动的本地进程；生产需遵守权限与变更流程
```

出现“偶发超时”时，比较连接池等待时间与网络连接时间：前者高说明应用资源排队，后者高才更像网络或下游问题。

## 抓包与证据

应用日志回答“代码走到哪里”，`curl -v` 回答“客户端看到了什么”，抓包回答“线上传了什么”。在有权限且经过审批的环境使用 `tcpdump`，只抓目标地址和短时间窗口，避免采集敏感 payload：

```bash
tcpdump -nn -i any 'host 10.0.0.8 and port 443' -c 100
```

TLS 加密后抓包通常只能看到握手、IP、端口和时序；不要声称抓包能直接读取 HTTPS 业务内容。优先使用脱敏后的 trace、指标和网关日志。

## 一张故障决策表

```txt
DNS 无结果？       → resolver / TTL / 容器 DNS
有 IP 但 connect 失败？ → 路由 / 安全组 / 监听 / backlog
TCP 成功 TLS 失败？    → 时间、SAN、SNI、链、ALPN
HTTP 4xx？             → 请求语义、鉴权、路由
HTTP 5xx？             → 产生者、上游、资源池、依赖
只有高并发才失败？     → 连接池、FD、队列、限流、backlog、GC
只有重试后数据异常？   → 幂等键、请求是否已执行、超时预算
```

每一步都留下可复现探针和时间窗口。修复后的成功响应不够，还要检查延迟分位数、错误率、连接池水位和业务副作用。

## 面试追问

- **为什么 ping 通但 HTTP 不通？** ping 是 ICMP，不能证明 TCP 端口、TLS 或 HTTP 路由可用。
- **客户端超时，服务端到底执行没有？** 不能从超时判断；用 request id、数据库记录和幂等键确认。
- **HTTP/2 一定更快吗？** 多路复用减少连接和队头阻塞，但服务端、代理、TLS、丢包和请求形态都影响结果。
- **重试放在哪里？** 只在明确的幂等边界放，设置总预算与退避，避免客户端、网关、SDK 多层叠加重试。
- **怎么证明是连接池问题？** 对比池等待、建立连接和服务处理三个时间；只看总耗时不能定位。
