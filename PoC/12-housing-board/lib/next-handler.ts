/* 기존 Node 핸들러(req, res)를 Next.js 라우트 핸들러(Request → Response)로 감싼다.
   핸들러(handlers/**)가 쓰는 면은 req.method · req.url · res.statusCode · res.setHeader · res.end 뿐이라 이 정도면 된다. 본문은 글자 또는 바이트(지형 타일 PNG, handlers/v1/terrain.js).
   핸들러와 lib/*.js(CJS)·그 시험은 그대로 두고, 응답 모양(상태·헤더·본문)이 같게 이어 주는 것이 목적이다. */
type NodeRes = {
  statusCode: number;
  setHeader(name: string, value: string | number | readonly string[]): void;
  end(chunk?: string | Uint8Array): void;
};
type NodeHandler = (req: { method: string; url: string }, res: NodeRes) => unknown;

export function toRoute(handler: NodeHandler) {
  return (request: Request): Promise<Response> =>
    new Promise<Response>((resolve) => {
      const u = new URL(request.url);
      const headers = new Headers();
      let done = false;
      const finish = (status: number, body: string | Uint8Array | null) => {
        if (done) return;
        done = true;
        const none = request.method === 'HEAD' || status === 204 || status === 304;
        resolve(new Response(none ? null : (body as BodyInit | null), { status, headers }));
      };
      const res: NodeRes = {
        statusCode: 200,
        setHeader: (name, value) => { headers.set(name, Array.isArray(value) ? value.join(', ') : String(value)); },
        end: (chunk) => finish(res.statusCode, chunk ?? null),
      };
      Promise.resolve(handler({ method: request.method, url: u.pathname + u.search }, res)).then(
        () => { if (!done) { headers.set('Cache-Control', 'no-store'); finish(500, null); } },   // 핸들러가 응답을 끝내지 않고 돌아온 경우
        () => { headers.set('Cache-Control', 'no-store'); finish(500, null); },                  // 핸들러 안의 예외는 본문 없이 500 (원천 오류 문구를 내보내지 않는다)
      );
    });
}

/* 핸들러가 405 와 Allow 를 직접 답하므로(스펙 3.1 공통 규칙) 모든 메서드를 같은 핸들러로 보낸다. */
export const allMethods = (route: (request: Request) => Promise<Response>) => ({
  GET: route, HEAD: route, POST: route, PUT: route, PATCH: route, DELETE: route, OPTIONS: route,
});
