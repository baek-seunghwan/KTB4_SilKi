const decodeBase64 = (payload) => {
  const base64 = payload.includes(",") ? payload.slice(payload.indexOf(",") + 1) : payload;
  const binary = window.atob(base64.replace(/\s/g, ""));
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
};

const SUPPORTED_MEDIA_TYPES = new Set(["audio/mpeg", "audio/wav", "audio/ogg"]);
const MAX_BASE64_LENGTH = 11_200_000;
const PLAYBACK_START_TIMEOUT_MS = 2_000;
const PLAYBACK_HARD_TIMEOUT_MS = 20_000;

const createPlaybackAbortError = () => {
  const error = new Error("안내 음성 재생이 취소되었습니다.");
  error.name = "AbortError";
  return error;
};

export const getTtsPayload = (message) => {
  const nested = typeof message.audio === "object" ? message.audio : null;
  const base64 =
    message.audioBase64 ||
    message.base64Audio ||
    message.data ||
    (typeof message.audio === "string" ? message.audio : null) ||
    nested?.base64 ||
    nested?.data;

  if (
    !base64 ||
    typeof base64 !== "string" ||
    base64.length > MAX_BASE64_LENGTH
  ) {
    return null;
  }

  const mimeType =
    message.mediaType ||
    message.mimeType ||
    message.contentType ||
    nested?.mediaType ||
    nested?.mimeType ||
    nested?.contentType ||
    "audio/wav";

  if (!SUPPORTED_MEDIA_TYPES.has(mimeType)) {
    return null;
  }

  return {
    base64,
    mimeType,
  };
};

export class TtsAudioPlayer {
  constructor() {
    this.audio = null;
    this.objectUrl = null;
    this.cancelPlayback = null;
  }

  stop() {
    const cancelPlayback = this.cancelPlayback;
    this.cancelPlayback = null;

    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
      this.audio = null;
    }

    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }

    cancelPlayback?.();
  }

  async play({ base64, mimeType }) {
    this.stop();
    const bytes = decodeBase64(base64);
    const blob = new Blob([bytes], { type: mimeType });
    this.objectUrl = URL.createObjectURL(blob);
    this.audio = new Audio(this.objectUrl);
    const audio = this.audio;

    try {
      await new Promise((resolve, reject) => {
        let settled = false;
        const startTimer = window.setTimeout(
          () => settle(reject, new Error("안내 음성 재생이 시작되지 않았습니다.")),
          PLAYBACK_START_TIMEOUT_MS,
        );
        const hardTimer = window.setTimeout(
          () => settle(reject, new Error("안내 음성 재생 시간이 초과되었습니다.")),
          PLAYBACK_HARD_TIMEOUT_MS,
        );

        const settle = (callback, value) => {
          if (settled) {
            return;
          }

          settled = true;
          window.clearTimeout(startTimer);
          window.clearTimeout(hardTimer);
          this.cancelPlayback = null;
          callback(value);
        };

        this.cancelPlayback = () => settle(reject, createPlaybackAbortError());
        audio.onplaying = () => window.clearTimeout(startTimer);
        audio.onended = () => settle(resolve);
        audio.onerror = () =>
          settle(reject, new Error("안내 음성을 재생하지 못했습니다."));
        audio.play().catch((error) => settle(reject, error));
      });
    } finally {
      if (this.audio === audio) {
        this.stop();
      }
    }
  }
}
