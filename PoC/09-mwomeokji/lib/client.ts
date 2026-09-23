export const base = "/poc/mwomeokji";
export const money = (value: number) => `${value.toLocaleString("ko-KR")}원`;

export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(
    `${base}/api/${path.includes("?") ? path.replace("?", "/?") : `${path}/`}`,
    {
      method,
      credentials: "same-origin",
      cache: "no-store",
      ...(data instanceof FormData
        ? { body: data }
        : data === undefined
          ? {}
          : {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(data),
            }),
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(payload.error || "잠시 후 다시 시도해 주세요.");
  return payload as T;
}
