import { Artifact, Message } from "./types";

export interface StreamCallbacks {
  onStatus?: (statusText: string) => void;
  onToken?: (token: string) => void;
  onDone?: (message: Message, artifacts: Artifact[]) => void;
  onError?: (err: Error) => void;
}

export async function streamMessage(
  sessionId: string,
  content: string,
  callbacks: StreamCallbacks
): Promise<void> {
  const url = `/api/sessions/${sessionId}/messages/stream`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || errData.error || `HTTP ${response.status}`);
    }

    if (!response.body) {
      throw new Error("ReadableStream not supported by browser.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) continue;

        let eventType = "message";
        let dataStr = "";

        const lines = block.split("\n");
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataStr = line.slice(5).trim();
          }
        }

        if (!dataStr) continue;

        try {
          const parsed = JSON.parse(dataStr);

          if (eventType === "status") {
            callbacks.onStatus?.(parsed.step || parsed.tool || "Working...");
          } else if (eventType === "token") {
            callbacks.onToken?.(parsed.delta || "");
          } else if (eventType === "done") {
            callbacks.onDone?.(parsed.message, parsed.artifacts || []);
          } else if (eventType === "error") {
            callbacks.onError?.(new Error(parsed.error || "Streaming error"));
          }
        } catch (e) {
          console.warn("Failed to parse SSE line:", dataStr, e);
        }
      }
    }
  } catch (err: any) {
    // Non-streaming fallback if stream endpoint failed
    console.warn("Streaming failed, falling back to standard API:", err);
    try {
      const fallbackRes = await fetch(`/api/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = await fallbackRes.json();
      if (!fallbackRes.ok) throw new Error(data.detail || data.error || "Request failed");
      callbacks.onDone?.(data.message, data.artifacts || []);
    } catch (fallbackErr: any) {
      callbacks.onError?.(fallbackErr);
    }
  }
}
