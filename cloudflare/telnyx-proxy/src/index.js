/**
 * Tiny Cloudflare Worker to give Telnyx a stable public hostname that forwards
 * directly to the NTC telephony endpoint on ntcnas.myftp.org.
 */

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const targetUrl = env.NTC_TELNYX_TARGET_URL;
    const publicBaseUrl = env.NTC_PUBLIC_BASE_URL || targetUrl;
    if (!targetUrl) {
      return new Response("NTC_TELNYX_TARGET_URL is not configured.", { status: 500 });
    }
    const telephonyTarget = new URL(targetUrl);
    const originTarget = new URL(publicBaseUrl);
    const target =
      incoming.pathname !== "/" && incoming.pathname !== ""
        ? new URL(`${incoming.pathname}${incoming.search}`, originTarget)
        : new URL(telephonyTarget.toString());

    if (incoming.pathname === "/" || incoming.pathname === "") {
      target.search = incoming.search;
    }

    const headers = new Headers(request.headers);
    headers.set("host", target.host);
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));
    headers.set("x-forwarded-for", request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for") || "");

    const init = {
      method: request.method,
      headers,
      redirect: "follow",
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
    };

    return fetch(target, init);
  },
};
