import { Artifact, Message } from "./types";

export interface StreamCallbacks {
  onStatus?: (statusText: string) => void;
  onToken?: (token: string) => void;
  onDone?: (message: Message, artifacts: Artifact[]) => void;
  onError?: (err: Error) => void;
}

/** Extract the joined `data:` payload from a single SSE event block. */
export function parseSseBlock(block: string): string | null {
  if (!block.trim()) return null;
  let dataStr = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("data:")) {
      dataStr += line.slice(5).trim();
    }
  }
  return dataStr || null;
}

async function fallbackToStandard(
  sessionId: string,
  content: string,
  callbacks: StreamCallbacks
): Promise<void> {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || "Request failed");
    callbacks.onDone?.(data.message, data.artifacts || []);
  } catch (err: any) {
    callbacks.onError?.(err);
  }
}

export async function streamMessage(
  sessionId: string,
  content: string,
  callbacks: StreamCallbacks
): Promise<void> {
  const url = `/api/sessions/${sessionId}/messages/stream`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content }),
    });
  } catch (err) {
    // The streaming endpoint is unreachable — fall back to the standard API.
    console.warn("Streaming endpoint unreachable, falling back:", err);
    return fallbackToStandard(sessionId, content, callbacks);
  }

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    callbacks.onError?.(
      new Error(errData.detail || errData.error || `HTTP ${response.status}`)
    );
    return;
  }

  if (!response.body) {
    callbacks.onError?.(new Error("ReadableStream not supported by browser."));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        const dataStr = parseSseBlock(block);
        if (!dataStr) continue;

        try {
          const parsed = JSON.parse(dataStr);
          const type: string = parsed.type || "message";

          switch (type) {
            case "status":
              callbacks.onStatus?.(parsed.data || parsed.step || parsed.tool || "Working...");
              break;
            case "token":
              callbacks.onToken?.(parsed.data || parsed.delta || "");
              break;
            case "done": {
              const payload = parsed.data || parsed;
              callbacks.onDone?.(payload.message, payload.artifacts || []);
              break;
            }
            case "error":
              callbacks.onError?.(new Error(parsed.data || parsed.error || "Streaming error"));
              break;
          }
        } catch (e) {
          console.warn("Failed to parse SSE line:", dataStr, e);
        }
      }
    }
  } catch (err) {
    // A mid-stream transport failure must NOT re-send the message (that would
    // duplicate the user + assistant turn). Surface an error instead.
    console.warn("Stream interrupted:", err);
    callbacks.onError?.(new Error("Connection interrupted while streaming. Please retry."));
  }
}
