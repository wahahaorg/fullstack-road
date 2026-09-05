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
