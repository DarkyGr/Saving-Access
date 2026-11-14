import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";

/** Build a rejected-request error like the ones axios throws for HTTP errors. */
export function httpError(status: number, detail = "error"): AxiosError {
  const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  return new AxiosError("Request failed", String(status), config, null, {
    status,
    statusText: String(status),
    data: { detail },
    headers: {},
    config,
  });
}
