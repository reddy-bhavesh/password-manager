export type ApiProblem = {
  title?: string;
  detail?: string;
  status?: number;
  type?: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly problem?: ApiProblem;

  constructor(status: number, message: string, problem?: ApiProblem) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

type JsonRequestOptions = {
  method: "GET" | "POST" | "PUT";
  body?: Record<string, unknown>;
  accessToken?: string | null;
  signal?: AbortSignal;
};

async function requestJson<TResponse>(path: string, options: JsonRequestOptions): Promise<TResponse> {
  const headers: Record<string, string> = {};

  if (options.body) {
    headers["Content-Type"] = "application/json";
  }

  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    headers,
    credentials: "include",
    signal: options.signal,
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? ((await response.json()) as unknown) : undefined;

  if (!response.ok) {
    const problem = (payload ?? {}) as ApiProblem;
    throw new ApiError(
      response.status,
      problem.detail ?? problem.title ?? `Request failed with status ${response.status}`,
      problem
    );
  }

  return payload as TResponse;
}

export async function getJson<TResponse>(
  path: string,
  options?: { accessToken?: string | null; signal?: AbortSignal }
): Promise<TResponse> {
  return requestJson<TResponse>(path, {
    method: "GET",
    accessToken: options?.accessToken,
    signal: options?.signal
  });
}

export async function postJson<TResponse, TBody extends Record<string, unknown>>(
  path: string,
  body: TBody,
  options?: { accessToken?: string | null; signal?: AbortSignal }
): Promise<TResponse> {
  return requestJson<TResponse>(path, {
    method: "POST",
    body,
    accessToken: options?.accessToken,
    signal: options?.signal
  });
}

export async function putJson<TResponse, TBody extends Record<string, unknown>>(
  path: string,
  body: TBody,
  options?: { accessToken?: string | null; signal?: AbortSignal }
): Promise<TResponse> {
  return requestJson<TResponse>(path, {
    method: "PUT",
    body,
    accessToken: options?.accessToken,
    signal: options?.signal
  });
}
