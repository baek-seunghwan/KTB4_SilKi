import { useCallback, useEffect, useRef, useState } from "react";
import { Pcm16Microphone } from "../lib/Pcm16Microphone";
import { getTtsPayload, TtsAudioPlayer } from "../lib/TtsAudioPlayer";
import {
  addCartItem,
  createOrderSession,
  getCart,
  getAiWebSocketUrl,
  getPublicMenu,
  issueAiAccessToken,
  toAiCartItems,
} from "../services/orderSessionApi";

const INITIAL_VIEW = {
  phase: "preparing",
  orderSessionId: null,
  isListening: false,
  isPlayingTts: false,
  statusMessage: "음성 주문을 준비하고 있어요",
  transcript: "",
  displayText: "",
  candidates: [],
  noMatchMessage: "",
  error: null,
  lastResult: null,
  cart: null,
  dialog: null,
  candidateActions: {},
  eventLog: [],
  audioStats: {
    framesSent: 0,
    bytesSent: 0,
    currentDbfs: null,
    peakDbfs: null,
  },
};

const READY_TIMEOUT_MS = 10_000;
const MAX_AUDIO_BUFFERED_BYTES = 512 * 1024;
const MIN_DBFS = -96;
const DIALOG_CAPABILITY = "dialog.v1";
const DIALOG_LISTEN_DELAY_MS = 400;
const DIALOG_TTS_WAIT_MS = 6_000;

const calculateDbfs = (frame) => {
  const samples = new Int16Array(frame);

  if (!samples.length) {
    return MIN_DBFS;
  }

  let sumSquares = 0;

  for (const sample of samples) {
    const normalized = sample / 32768;
    sumSquares += normalized * normalized;
  }

  const rms = Math.sqrt(sumSquares / samples.length);
  return rms > 0 ? Math.max(MIN_DBFS, 20 * Math.log10(rms)) : MIN_DBFS;
};

const getCandidateOptionPlan = (menu, attributes = {}, explicitSelections = {}) => {
  const optionValueIds = [];
  const requiredOptions = [];
  const selectionByGroup = {};

  for (const group of Array.isArray(menu?.options) ? menu.options : []) {
    const allowedValues = Array.isArray(group.values) ? group.values : [];
    const allowedIds = new Set(allowedValues.map((value) => String(value.id)));
    const explicitIds = Array.isArray(explicitSelections[group.id])
      ? explicitSelections[group.id].map(String).filter((id) => allowedIds.has(id))
      : [];
    let selectedIds = explicitIds;

    if (!selectedIds.length && group.code === "TEMPERATURE" && attributes.temperature) {
      const temperature = allowedValues.find(
        (value) => value.code === String(attributes.temperature).toUpperCase(),
      );
      selectedIds = temperature ? [String(temperature.id)] : [];
    }

    if (!selectedIds.length && group.autoSelectedOptionId) {
      selectedIds = [String(group.autoSelectedOptionId)];
    }

    const maximum = Number.isInteger(group.maxSelections) ? group.maxSelections : 1;
    selectedIds = selectedIds.slice(0, Math.max(0, maximum));
    selectionByGroup[group.id] = selectedIds;

    if (group.requiresSelection) {
      requiredOptions.push(group);
    }

    optionValueIds.push(...selectedIds);
  }

  return { optionValueIds, requiredOptions, selectionByGroup };
};

const getProposalOptionPlan = (
  menu,
  resolvedOptions = [],
  attributes = {},
  explicitOptionIds = [],
) => {
  const explicitSelections = {};
  const explicitIds = new Set(explicitOptionIds.map(String));

  for (const group of Array.isArray(menu?.options) ? menu.options : []) {
    const resolved = resolvedOptions.find(
      (item) => String(item?.groupCode || "").toUpperCase() === String(group.code).toUpperCase(),
    );
    const selected = resolved
      ? group.values?.find(
          (value) =>
            String(value.code || "").toUpperCase() ===
            String(resolved.valueCode || "").toUpperCase(),
        )
      : null;

    const selectedById = group.values?.filter((value) => explicitIds.has(String(value.id))) || [];
    if (selectedById.length || selected) {
      explicitSelections[group.id] = selectedById.length
        ? selectedById.map((value) => String(value.id))
        : [String(selected.id)];
    }
  }

  const plan = getCandidateOptionPlan(menu, attributes, explicitSelections);
  const unresolved = plan.requiredOptions.filter((group) => {
    const count = plan.selectionByGroup[group.id]?.length || 0;
    return count < Math.max(1, group.minSelections || 0) || count > group.maxSelections;
  });
  const selectedOptions = [];

  for (const group of Array.isArray(menu?.options) ? menu.options : []) {
    const selectedIds = new Set(plan.selectionByGroup[group.id] || []);
    for (const value of Array.isArray(group.values) ? group.values : []) {
      if (selectedIds.has(String(value.id))) {
        selectedOptions.push({
          groupId: String(group.id),
          groupCode: group.code,
          groupName: group.name,
          id: String(value.id),
          code: value.code,
          name: value.name,
          additionalPrice: Number(value.additionalPrice || 0),
        });
      }
    }
  }

  return { ...plan, selectedOptions, unresolved };
};

const sameDialog = (left, right) =>
  Boolean(
    left &&
      right &&
      left.conversationId === right.conversationId &&
      left.dialogId === right.dialogId &&
      left.revision === right.revision,
  );

const getDialogTtsPurpose = (dialog) => {
  if (dialog?.type === "clarification") return "clarification";
  if (dialog?.type === "proposal") return "proposal";
  if (dialog?.type === "success") return "completion";
  return null;
};

const sameDialogTts = (dialog, message) =>
  sameDialog(dialog, message) && getDialogTtsPurpose(dialog) === message?.purpose;

const normalizeCandidates = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }

  const seenMenuIds = new Set();

  return value.flatMap((candidate) => {
    const menuId = String(candidate?.menuId || "").trim();
    const name = String(candidate?.name || "").trim();

    if (!menuId || !name || seenMenuIds.has(menuId)) {
      return [];
    }

    seenMenuIds.add(menuId);
    return [
      {
        menuId,
        name,
        description: String(candidate?.description || "").trim(),
        score: Number.isFinite(candidate?.score) ? candidate.score : null,
        matchedAttributes: Array.isArray(candidate?.matchedAttributes)
          ? candidate.matchedAttributes
              .map((attribute) => String(attribute).trim())
              .filter(Boolean)
          : [],
      },
    ];
  });
};

const summarizeEvent = (message) => {
  switch (message.type) {
    case "turn.started":
      return "발화 감지";
    case "stt.partial":
      return `중간 인식: ${(message.text || "").slice(0, 60)}`;
    case "turn.final":
      return `최종 인식: ${(message.text || "").slice(0, 60)}`;
    case "menu.candidates":
      return `메뉴 후보 ${message.candidates?.length || 0}개`;
    case "no_match":
      return "조건에 맞는 후보 없음";
    case "tts.audio":
      return `TTS 수신: ${message.mediaType || "audio"}`;
    case "tts.unavailable":
      return "서버 TTS 불가 · 브라우저 대체 음성 사용";
    case "dialog.clarification":
      return `추가 질문: ${(message.text || "").slice(0, 60)}`;
    case "dialog.proposal":
      return `최종 제안: ${message.menu?.name || "메뉴"}`;
    case "dialog.completed":
      return "장바구니 반영 완료";
    case "dialog.action":
      return `음성 선택: ${message.action || "알 수 없음"}`;
    case "error":
      return `${message.code || "AI_ERROR"}: ${message.message || "오류"}`;
    default:
      return "서버 이벤트 수신";
  }
};

const getFriendlyError = (error) => {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "마이크 권한을 허용한 뒤 다시 시도해주세요.";
  }

  if (error?.name === "NotFoundError") {
    return "사용할 수 있는 마이크를 찾지 못했습니다.";
  }

  return error?.message || "음성 주문을 시작하지 못했습니다.";
};

const waitForSocketOpen = (socket) =>
  new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("AI 음성 서버 연결 시간이 초과되었습니다."));
    }, READY_TIMEOUT_MS);

    const cleanup = () => {
      window.clearTimeout(timer);
      socket.removeEventListener("open", handleOpen);
      socket.removeEventListener("error", handleError);
      socket.removeEventListener("close", handleClose);
    };

    const handleOpen = () => {
      cleanup();
      resolve();
    };
    const handleError = () => {
      cleanup();
      reject(new Error("AI 음성 서버에 연결할 수 없습니다."));
    };
    const handleClose = () => {
      cleanup();
      reject(new Error("AI 음성 서버 연결이 시작 전에 종료되었습니다."));
    };

    socket.addEventListener("open", handleOpen);
    socket.addEventListener("error", handleError);
    socket.addEventListener("close", handleClose);
  });

const createReadyWaiter = () => {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  const timer = window.setTimeout(() => {
    reject(new Error("AI 음성 세션 인증 시간이 초과되었습니다."));
  }, READY_TIMEOUT_MS);

  return {
    promise: promise.finally(() => window.clearTimeout(timer)),
    resolve,
    reject,
  };
};

export const useVoiceOrderSession = (
  storeId,
  initialOrderSessionId = "",
  onFinishVoiceOrder = null,
) => {
  const [view, setView] = useState(INITIAL_VIEW);
  const mountedRef = useRef(false);
  const connectionAttemptRef = useRef(0);
  const abortControllerRef = useRef(null);
  const socketRef = useRef(null);
  const expectedCloseSocketsRef = useRef(new WeakSet());
  const microphoneRef = useRef(null);
  const playerRef = useRef(new TtsAudioPlayer());
  const orderSessionRef = useRef(null);
  const aiSessionIdRef = useRef(null);
  const pendingResultTurnIdRef = useRef(null);
  const ignoredTurnIdsRef = useRef(new Set());
  const requiresFreshConnectionRef = useRef(false);
  const ttsPlaybackIdRef = useRef(0);
  const activeDialogRef = useRef(null);
  const dialogTtsTimerRef = useRef(null);
  const dialogListenTimerRef = useRef(null);
  const pendingDialogTtsRef = useRef(new Map());
  const consumedDialogTtsRef = useRef(new Set());
  const openedDialogListenRef = useRef(new Set());
  const replayDialogAudioRef = useRef(null);
  const proposalLoadRef = useRef(0);
  const handledDialogActionsRef = useRef(new Set());
  const dialogActionHandlersRef = useRef({});
  const startMicrophoneRef = useRef(null);
  const listeningIntentRef = useRef(true);
  const audioStatsRef = useRef({
    framesSent: 0,
    bytesSent: 0,
    currentDbfs: null,
    peakDbfs: null,
  });

  const updateView = useCallback((next) => {
    if (!mountedRef.current) {
      return;
    }

    setView((current) => ({
      ...current,
      ...(typeof next === "function" ? next(current) : next),
    }));
  }, []);

  const pushDiagnosticEvent = useCallback(
    (type, detail) => {
      updateView((current) => ({
        eventLog: [
          ...current.eventLog,
          {
            id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
            time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
            type,
            detail,
          },
        ].slice(-12),
      }));
    },
    [updateView],
  );

  const clearDialogTimers = useCallback(() => {
    window.clearTimeout(dialogTtsTimerRef.current);
    window.clearTimeout(dialogListenTimerRef.current);
    dialogTtsTimerRef.current = null;
    dialogListenTimerRef.current = null;
  }, []);

  const setActiveDialog = useCallback(
    (dialog) => {
      if (!sameDialog(activeDialogRef.current, dialog)) {
        replayDialogAudioRef.current = null;
      }
      activeDialogRef.current = dialog;
      updateView({ dialog });
    },
    [updateView],
  );

  const sendDialogControl = useCallback((type, dialog, extra = {}) => {
    const socket = socketRef.current;

    if (
      !dialog ||
      socket?.readyState !== WebSocket.OPEN ||
      !aiSessionIdRef.current
    ) {
      return false;
    }

    socket.send(
      JSON.stringify({
        type,
        sessionId: aiSessionIdRef.current,
        conversationId: dialog.conversationId,
        dialogId: dialog.dialogId,
        revision: dialog.revision,
        ...extra,
      }),
    );
    pushDiagnosticEvent(type, `대화 r${dialog.revision}`);
    return true;
  }, [pushDiagnosticEvent]);

  const applyCartSnapshot = useCallback(
    (cart, { notifyAi = true } = {}) => {
      if (!Number.isInteger(cart?.cartVersion) || !Array.isArray(cart?.items)) {
        throw new Error("Spring 장바구니 응답 형식이 올바르지 않습니다.");
      }

      orderSessionRef.current = orderSessionRef.current
        ? { ...orderSessionRef.current, cartVersion: cart.cartVersion }
        : orderSessionRef.current;
      updateView({ cart });

      const socket = socketRef.current;

      if (
        notifyAi &&
        socket?.readyState === WebSocket.OPEN &&
        aiSessionIdRef.current
      ) {
        socket.send(
          JSON.stringify({
            type: "cart.context",
            sessionId: aiSessionIdRef.current,
            basedOnCartVersion: cart.cartVersion,
            cartItems: toAiCartItems(cart),
          }),
        );
        pushDiagnosticEvent(
          "cart.context",
          `장바구니 v${cart.cartVersion} · ${cart.totalQuantity || 0}개 동기화`,
        );
      }
    },
    [pushDiagnosticEvent, updateView],
  );

  const closeSocket = useCallback((socket, { sendSessionEnd = false } = {}) => {
    if (!socket) {
      return;
    }

    expectedCloseSocketsRef.current.add(socket);

    if (socket.readyState === WebSocket.OPEN) {
      if (sendSessionEnd && aiSessionIdRef.current) {
        socket.send(
          JSON.stringify({
            type: "session.end",
            sessionId: aiSessionIdRef.current,
            reason: "client_navigation",
          }),
        );
      }

      socket.close(1000, "session complete");
    } else if (socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
  }, []);

  const stopRealtimeResources = useCallback(
    ({ sendSessionEnd = false } = {}) => {
      clearDialogTimers();
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;

      const microphone = microphoneRef.current;
      microphoneRef.current = null;
      microphone?.stop().catch(() => {});

      playerRef.current.stop();
      window.speechSynthesis?.cancel();
      ttsPlaybackIdRef.current += 1;
      closeSocket(socketRef.current, { sendSessionEnd });
      socketRef.current = null;
      aiSessionIdRef.current = null;
      pendingResultTurnIdRef.current = null;
      ignoredTurnIdsRef.current.clear();
      requiresFreshConnectionRef.current = false;
      activeDialogRef.current = null;
      pendingDialogTtsRef.current.clear();
      consumedDialogTtsRef.current.clear();
      openedDialogListenRef.current.clear();
      handledDialogActionsRef.current.clear();
      replayDialogAudioRef.current = null;
      proposalLoadRef.current += 1;
    },
    [clearDialogTimers, closeSocket],
  );

  const scheduleDialogListen = useCallback(
    (dialog, delay = DIALOG_LISTEN_DELAY_MS) => {
      window.clearTimeout(dialogListenTimerRef.current);
      dialogListenTimerRef.current = window.setTimeout(async () => {
        if (!sameDialog(activeDialogRef.current, dialog)) {
          return;
        }
        const canListen =
          !dialog.localOnly &&
          ["clarification", "proposal", "success"].includes(dialog.type);
        if (!canListen) return;
        const correlationKey = `${dialog.conversationId}:${dialog.dialogId}:${dialog.revision}`;
        if (!openedDialogListenRef.current.has(correlationKey)) {
          if (!sendDialogControl("dialog.listen", dialog)) {
            const current = activeDialogRef.current;
            if (sameDialog(current, dialog)) {
              const next = { ...current, isBusy: false };
              activeDialogRef.current = next;
              updateView({
                dialog: next,
                isListening: false,
                phase: "error",
                statusMessage: "음성 연결을 다시 시작해주세요",
              });
            }
            return;
          }
          openedDialogListenRef.current.add(correlationKey);
        }

        listeningIntentRef.current = true;
        try {
          await startMicrophoneRef.current?.();
          const current = activeDialogRef.current;
          if (sameDialog(current, dialog)) {
            const next = { ...current, isBusy: false };
            activeDialogRef.current = next;
            updateView({
              dialog: next,
              isListening: true,
              phase: "listening",
              statusMessage: "답변을 듣고 있어요",
              transcript: "",
              displayText: "",
            });
          }
        } catch (error) {
          updateView({
            phase: "error",
            error: {
              code: "MICROPHONE_FAILED",
              message: getFriendlyError(error),
              retryable: true,
            },
          });
        }
      }, delay);
    },
    [sendDialogControl, updateView],
  );

  const playDialogSpeech = useCallback(
    async (dialog, payload = null) => {
      if (!sameDialog(activeDialogRef.current, dialog)) return;
      clearDialogTimers();
      const playbackId = ttsPlaybackIdRef.current + 1;
      ttsPlaybackIdRef.current = playbackId;
      playerRef.current.stop();
      window.speechSynthesis?.cancel();
      listeningIntentRef.current = false;
      microphoneRef.current?.pause();
      const playingDialog = { ...activeDialogRef.current, isBusy: true };
      activeDialogRef.current = playingDialog;
      updateView({
        dialog: playingDialog,
        isListening: false,
        isPlayingTts: true,
        statusMessage: "안내 중이에요",
        displayText: dialog.text || "",
      });

      let played = false;
      try {
        if (payload) {
          replayDialogAudioRef.current = { dialog, payload };
          await playerRef.current.play(payload);
          played = true;
        }
      } catch {
        played = false;
      } finally {
        if (
          playbackId === ttsPlaybackIdRef.current &&
          sameDialog(activeDialogRef.current, dialog)
        ) {
          const current = activeDialogRef.current;
          const shouldListen =
            !dialog.localOnly &&
            ["clarification", "proposal", "success"].includes(dialog.type);
          const nextDialog = {
            ...current,
            isBusy: shouldListen,
            ttsPlaybackFailed: !played,
          };
          activeDialogRef.current = nextDialog;
          pushDiagnosticEvent(
            played ? "tts.played" : "tts.fallback.available",
            played
              ? payload
                ? "서버 안내 음성 재생 완료"
                : "브라우저 안내 음성 재생 완료"
              : "자동 안내 재생 실패 · 안내 다시 듣기 사용 가능",
          );
          updateView({
            dialog: nextDialog,
            isListening: false,
            isPlayingTts: false,
            statusMessage:
              dialog.localOnly
                ? "옵션을 선택해주세요"
                : shouldListen
                  ? "곧 답변을 들을게요"
                  : "메뉴를 확인해주세요",
          });
          if (shouldListen) {
            scheduleDialogListen(dialog);
          }
        }
      }
    },
    [clearDialogTimers, pushDiagnosticEvent, scheduleDialogListen, updateView],
  );

  const replayDialogSpeech = useCallback(() => {
    const dialog = activeDialogRef.current;
    if (
      !dialog ||
      dialog.type === "submitting" ||
      dialog.isSubmitting ||
      view.isPlayingTts
    ) {
      return;
    }

    const cached = replayDialogAudioRef.current;
    const payload = cached && sameDialog(cached.dialog, dialog) ? cached.payload : null;
    void playDialogSpeech(dialog, payload);
  }, [playDialogSpeech, view.isPlayingTts]);

  const waitForDialogTts = useCallback(
    (dialog) => {
      clearDialogTimers();
      const correlationKey = `${dialog.conversationId}:${dialog.dialogId}:${dialog.revision}`;
      if (consumedDialogTtsRef.current.has(correlationKey)) {
        return;
      }
      const pending = pendingDialogTtsRef.current.get(dialog.dialogId);
      if (pending && sameDialogTts(dialog, pending)) {
        pendingDialogTtsRef.current.delete(dialog.dialogId);
        consumedDialogTtsRef.current.add(correlationKey);
        void playDialogSpeech(dialog, getTtsPayload(pending));
        return;
      }
      if (!dialog.ttsExpected) {
        consumedDialogTtsRef.current.add(correlationKey);
        void playDialogSpeech(dialog);
        return;
      }
      dialogTtsTimerRef.current = window.setTimeout(() => {
        if (sameDialog(activeDialogRef.current, dialog)) {
          consumedDialogTtsRef.current.add(correlationKey);
          void playDialogSpeech(dialog);
        }
      }, DIALOG_TTS_WAIT_MS);
    },
    [clearDialogTimers, playDialogSpeech],
  );

  const presentProposal = useCallback(
    (message, menu, explicitOptionIds = [], { useRemoteTts = true } = {}) => {
      const plan = getProposalOptionPlan(
        menu,
        message.resolvedOptions,
        message.attributes,
        explicitOptionIds,
      );

      if (plan.unresolved.length) {
        const group = plan.unresolved[0];
        const localDialog = {
          type: "clarification",
          conversationId: message.conversationId,
          dialogId: message.dialogId,
          revision: message.revision,
          turnId: message.turnId,
          basedOnCartVersion: message.basedOnCartVersion,
          text: `${group.name} 옵션을 선택해주세요.`,
          choices: group.values.map((value) => ({
            id: `local:${group.id}:${value.id}`,
            label: value.name,
            value: String(value.id),
          })),
          ttsExpected: false,
          localOnly: true,
          suppressRemoteTts: true,
          proposalMessage: message,
          menu,
          explicitOptionIds,
        };
        setActiveDialog(localDialog);
        updateView({
          phase: "result",
          isListening: false,
          statusMessage: "필수 옵션을 선택해주세요",
        });
        void playDialogSpeech(localDialog);
        return;
      }

      const quantity = message.quantity || 1;
      const unitPrice = Number(menu.price || 0) + plan.selectedOptions.reduce(
        (sum, option) => sum + option.additionalPrice,
        0,
      );
      const proposal = {
        type: "proposal",
        conversationId: message.conversationId,
        dialogId: message.dialogId,
        revision: message.revision,
        turnId: message.turnId,
        basedOnCartVersion: message.basedOnCartVersion,
        text: message.text,
        ttsExpected: useRemoteTts && message.ttsExpected,
        menu: {
          ...menu,
          menuId: String(menu.id),
        },
        quantity,
        attributes: message.attributes || {},
        resolvedOptions: message.resolvedOptions || [],
        optionValueIds: plan.optionValueIds,
        selectedOptions: plan.selectedOptions,
        totalPrice: unitPrice * quantity,
        degraded: Boolean(message.degraded),
      };
      setActiveDialog(proposal);
      updateView({
        phase: "result",
        candidates: [],
        candidateActions: {},
        noMatchMessage: "",
        error: null,
        statusMessage: "추천 메뉴를 확인해주세요",
      });
      waitForDialogTts(proposal);
    },
    [playDialogSpeech, setActiveDialog, updateView, waitForDialogTts],
  );

  const loadDialogProposal = useCallback(
    async (message) => {
      clearDialogTimers();
      listeningIntentRef.current = false;
      microphoneRef.current?.pause();
      const requestId = proposalLoadRef.current + 1;
      proposalLoadRef.current = requestId;
      const loadingDialog = {
        type: "proposal",
        conversationId: message.conversationId,
        dialogId: message.dialogId,
        revision: message.revision,
        turnId: message.turnId,
        basedOnCartVersion: message.basedOnCartVersion,
        text: message.text,
        ttsExpected: message.ttsExpected,
        menu: { name: message.menu?.name || "메뉴 정보를 확인하고 있어요" },
        quantity: message.quantity || 1,
        isLoading: true,
      };
      setActiveDialog(loadingDialog);
      updateView({ isListening: false, phase: "processing", statusMessage: "메뉴 정보를 확인하고 있어요" });

      try {
        const menuId = String(message.menu?.menuId || "").trim();
        const menu = await getPublicMenu(storeId, menuId);
        if (requestId !== proposalLoadRef.current || !sameDialog(activeDialogRef.current, loadingDialog)) {
          return;
        }
        if (String(menu?.id) !== menuId || menu.salesStatus !== "AVAILABLE") {
          throw new Error("현재 판매 중인 추천 메뉴 정보를 확인할 수 없습니다.");
        }
        if (message.basedOnCartVersion !== orderSessionRef.current?.cartVersion) {
          throw new Error("장바구니가 변경되어 추천을 다시 확인해야 합니다.");
        }
        presentProposal(message, menu);
      } catch (error) {
        if (requestId !== proposalLoadRef.current) return;
        const failed = {
          ...loadingDialog,
          isLoading: false,
          error: getFriendlyError(error),
        };
        setActiveDialog(failed);
        updateView({ phase: "error", statusMessage: "추천 메뉴를 확인하지 못했어요" });
      }
    },
    [clearDialogTimers, presentProposal, setActiveDialog, storeId, updateView],
  );

  const handleServerMessage = useCallback(
    (message) => {
      if (
        message.type !== "turn.started" &&
        message.turnId &&
        ignoredTurnIdsRef.current.has(message.turnId)
      ) {
        pushDiagnosticEvent(
          "turn.ignored",
          `마이크 중지 후 도착한 버퍼 이벤트 무시: ${message.type}`,
        );
        return;
      }

      pushDiagnosticEvent(message.type, summarizeEvent(message));

      switch (message.type) {
        case "turn.started":
          if (!listeningIntentRef.current) {
            ignoredTurnIdsRef.current.add(message.turnId);
            requiresFreshConnectionRef.current = true;
            pushDiagnosticEvent(
              "turn.ignored",
              "마이크 중지 후 시작된 버퍼 턴 무시 · 다음 시작 시 새 연결 사용",
            );
            break;
          }

          pendingResultTurnIdRef.current = null;
          updateView({
            phase: "listening",
            transcript: "",
            displayText: "",
            candidates: [],
            noMatchMessage: "",
            error: null,
            lastResult: null,
            candidateActions: {},
            statusMessage: "말씀을 듣고 있어요",
          });
          break;
        case "stt.partial":
          if (!listeningIntentRef.current) {
            break;
          }

          updateView({
            phase: "listening",
            transcript: message.text || "",
            displayText: message.text || "",
            statusMessage: "말씀을 인식하고 있어요",
          });
          break;
        case "turn.final":
          pendingResultTurnIdRef.current = message.turnId;
          listeningIntentRef.current = false;
          microphoneRef.current?.pause();
          audioStatsRef.current.currentDbfs = null;
          updateView({
            phase: "processing",
            isListening: false,
            transcript: message.text || "",
            displayText: message.text || "",
            audioStats: { ...audioStatsRef.current },
            statusMessage: "메뉴를 찾고 있어요",
          });
          break;
        case "dialog.clarification": {
          pendingResultTurnIdRef.current = null;
          clearDialogTimers();
          playerRef.current.stop();
          window.speechSynthesis?.cancel();
          ttsPlaybackIdRef.current += 1;
          listeningIntentRef.current = false;
          microphoneRef.current?.pause();
          const isMenuChoice = message.missingSlot === "menu";
          const clarification = {
            type: "clarification",
            conversationId: message.conversationId,
            dialogId: message.dialogId,
            revision: message.revision,
            turnId: message.turnId,
            basedOnCartVersion: message.basedOnCartVersion,
            text: message.text,
            missingSlot: message.missingSlot,
            choices: Array.isArray(message.choices)
              ? isMenuChoice
                ? message.choices.slice(0, 2)
                : message.choices
              : [],
            accumulatedSlots: message.accumulatedSlots || null,
            ttsExpected: Boolean(message.ttsExpected),
            isBusy: true,
          };
          setActiveDialog(clarification);
          updateView({
            phase: "result",
            isListening: false,
            candidates: [],
            candidateActions: {},
            noMatchMessage: "",
            error: null,
            statusMessage: "추가 질문을 확인해주세요",
          });
          waitForDialogTts(clarification);
          break;
        }
        case "dialog.proposal":
          pendingResultTurnIdRef.current = null;
          void loadDialogProposal(message);
          break;
        case "dialog.completed": {
          pendingResultTurnIdRef.current = null;
          const active = activeDialogRef.current;
          if (
            !active ||
            active.conversationId !== message.conversationId ||
            active.dialogId !== message.dialogId ||
            message.revision < active.revision
          ) {
            pushDiagnosticEvent("dialog.ignored", "현재 제안과 다른 완료 응답 무시");
            break;
          }
          const completed = {
            ...active,
            type: "success",
            revision: message.revision,
            turnId: message.turnId,
            text: message.text || "장바구니에 담았어요. 더 주문하시겠어요?",
            ttsExpected: Boolean(message.ttsExpected),
            menuName: active.menu?.name,
            isBusy: true,
          };
          setActiveDialog(completed);
          updateView({
            phase: "result",
            statusMessage: "장바구니에 담았어요",
            displayText: completed.text,
          });
          waitForDialogTts(completed);
          break;
        }
        case "dialog.action": {
          pendingResultTurnIdRef.current = null;
          const active = activeDialogRef.current;
          const expectedDialogType = {
            accept: "proposal",
            reject: "proposal",
            continue: "success",
            finish: "success",
          }[message.action];

          if (
            !expectedDialogType ||
            !sameDialog(active, message) ||
            active.type !== expectedDialogType
          ) {
            pushDiagnosticEvent("dialog.ignored", "현재 질문과 다른 음성 선택 무시");
            break;
          }

          const actionKey =
            `${message.conversationId}:${message.dialogId}:${message.revision}:${message.action}`;
          if (handledDialogActionsRef.current.has(actionKey)) {
            pushDiagnosticEvent("dialog.ignored", "이미 처리한 음성 선택 무시");
            break;
          }

          const handler = dialogActionHandlersRef.current[message.action];
          if (typeof handler !== "function") {
            pushDiagnosticEvent("dialog.ignored", "연결되지 않은 음성 선택 무시");
            break;
          }

          handledDialogActionsRef.current.add(actionKey);
          void handler();
          break;
        }
        case "menu.candidates": {
          if (pendingResultTurnIdRef.current !== message.turnId) {
            pushDiagnosticEvent(
              "result.ignored",
              "현재 확정 발화와 다른 메뉴 후보를 무시",
            );
            break;
          }

          pendingResultTurnIdRef.current = null;
          const currentVersion = orderSessionRef.current?.cartVersion;
          const candidates = normalizeCandidates(message.candidates);

          if (
            Number.isInteger(currentVersion) &&
            message.basedOnCartVersion !== currentVersion
          ) {
            updateView({
              phase: "error",
              candidates: [],
              error: {
                code: "STALE_CART_CONTEXT",
                message: "주문 정보가 변경되어 추천 결과를 사용할 수 없습니다. 다시 말씀해주세요.",
                retryable: true,
              },
              statusMessage: "추천 결과를 다시 요청해주세요",
            });
            break;
          }

          updateView({
            phase: "result",
            candidates,
            candidateActions: {},
            noMatchMessage: "",
            error: null,
            lastResult: {
              turnId: message.turnId || "",
              basedOnCartVersion: message.basedOnCartVersion,
              searchQuery: message.searchQuery || "",
              quantity: message.quantity || 1,
              attributes: message.attributes || {},
              degraded: Boolean(message.degraded),
              candidateCount: candidates.length,
            },
            statusMessage: "추천 메뉴를 찾았어요",
          });
          break;
        }
        case "no_match":
          if (pendingResultTurnIdRef.current !== message.turnId) {
            pushDiagnosticEvent(
              "result.ignored",
              "현재 확정 발화와 다른 후보 없음 응답을 무시",
            );
            break;
          }

          pendingResultTurnIdRef.current = null;
          if (
            Number.isInteger(orderSessionRef.current?.cartVersion) &&
            message.basedOnCartVersion !== orderSessionRef.current.cartVersion
          ) {
            updateView({
              phase: "error",
              noMatchMessage: "",
              error: {
                code: "STALE_CART_CONTEXT",
                message: "주문 정보가 변경되어 검색 결과를 사용할 수 없습니다. 다시 말씀해주세요.",
                retryable: true,
              },
              statusMessage: "검색을 다시 요청해주세요",
            });
            break;
          }

          updateView({
            phase: "result",
            candidates: [],
            candidateActions: {},
            noMatchMessage:
              message.message || "조건에 맞는 메뉴를 찾지 못했어요. 다시 말씀해주세요.",
            error: null,
            lastResult: {
              turnId: message.turnId || "",
              basedOnCartVersion: message.basedOnCartVersion,
              searchQuery: message.searchQuery || "",
              quantity: message.quantity || 1,
              attributes: message.attributes || {},
              degraded: Boolean(message.degraded),
              candidateCount: 0,
            },
            statusMessage: "다른 메뉴를 말씀해주세요",
          });
          break;
        case "tts.audio": {
          const active = activeDialogRef.current;
          if (!message.dialogId || !message.conversationId || !Number.isInteger(message.revision)) {
            break;
          }
          if (!sameDialog(active, message) || active.isLoading) {
            pendingDialogTtsRef.current.set(message.dialogId, message);
            break;
          }
          if (!sameDialogTts(active, message)) {
            pushDiagnosticEvent("tts.ignored", "현재 질문 목적과 다른 안내 음성 무시");
            break;
          }
          if (active.suppressRemoteTts) break;
          const correlationKey =
            `${message.conversationId}:${message.dialogId}:${message.revision}`;
          if (consumedDialogTtsRef.current.has(correlationKey)) {
            const payload = getTtsPayload(message);
            if (payload) {
              replayDialogAudioRef.current = { dialog: active, payload };
            }
            break;
          }
          window.clearTimeout(dialogTtsTimerRef.current);
          dialogTtsTimerRef.current = null;
          consumedDialogTtsRef.current.add(correlationKey);
          void playDialogSpeech(active, getTtsPayload(message));
          break;
        }
        case "tts.unavailable": {
          const active = activeDialogRef.current;
          if (sameDialog(active, message) && active.isLoading) {
            pendingDialogTtsRef.current.set(message.dialogId, message);
            break;
          }
          if (!sameDialogTts(active, message) || active.suppressRemoteTts) break;
          const correlationKey =
            `${message.conversationId}:${message.dialogId}:${message.revision}`;
          if (consumedDialogTtsRef.current.has(correlationKey)) break;
          window.clearTimeout(dialogTtsTimerRef.current);
          dialogTtsTimerRef.current = null;
          consumedDialogTtsRef.current.add(correlationKey);
          void playDialogSpeech(active);
          break;
        }
        case "error":
          clearDialogTimers();
          activeDialogRef.current = null;
          updateView({
            phase: message.retryable ? "ready" : "error",
            dialog: null,
            error: {
              code: message.code || "AI_ERROR",
              message: message.message || "음성 처리 중 문제가 발생했습니다.",
              retryable: Boolean(message.retryable),
            },
            statusMessage: message.retryable
              ? "다시 말씀하거나 연결을 다시 시도해주세요"
              : "음성 주문을 계속할 수 없습니다",
          });
          break;
        default:
          break;
      }
    },
    [
      clearDialogTimers,
      loadDialogProposal,
      playDialogSpeech,
      pushDiagnosticEvent,
      setActiveDialog,
      updateView,
      waitForDialogTts,
    ],
  );

  const startMicrophone = useCallback(async () => {
    const socket = socketRef.current;

    if (!socket || socket.readyState !== WebSocket.OPEN || !aiSessionIdRef.current) {
      throw new Error("AI 음성 세션이 아직 준비되지 않았습니다.");
    }

    if (microphoneRef.current) {
      listeningIntentRef.current = true;
      ignoredTurnIdsRef.current.clear();
      await microphoneRef.current.resume();
      if (
        socketRef.current !== socket ||
        socket.readyState !== WebSocket.OPEN ||
        !aiSessionIdRef.current
      ) {
        return;
      }
      updateView({
        phase: "listening",
        isListening: true,
        error: null,
        statusMessage: "실키가 잘 듣고 있어요",
        displayText: "",
      });
      return;
    }

    const microphone = new Pcm16Microphone({
      onFrame: (frame) => {
        const activeSocket = socketRef.current;

        if (
          listeningIntentRef.current &&
          activeSocket?.readyState === WebSocket.OPEN &&
          activeSocket.bufferedAmount < MAX_AUDIO_BUFFERED_BYTES
        ) {
          activeSocket.send(frame);
          const stats = audioStatsRef.current;
          stats.framesSent += 1;
          stats.bytesSent += frame.byteLength;
          stats.currentDbfs = calculateDbfs(frame);
          stats.peakDbfs =
            stats.peakDbfs === null
              ? stats.currentDbfs
              : Math.max(stats.peakDbfs, stats.currentDbfs);
          if (stats.framesSent === 1 || stats.framesSent % 10 === 0) {
            updateView({ audioStats: { ...stats } });
          }
        }
      },
      onError: (error) => {
        updateView({
          phase: "error",
          isListening: false,
          error: {
            code: "AUDIO_CAPTURE_FAILED",
            message: getFriendlyError(error),
            retryable: true,
          },
          statusMessage: "마이크를 다시 시작해주세요",
        });
      },
    });
    microphoneRef.current = microphone;

    try {
      listeningIntentRef.current = true;
      ignoredTurnIdsRef.current.clear();
      await microphone.start();
      if (
        microphoneRef.current !== microphone ||
        socketRef.current !== socket ||
        socket.readyState !== WebSocket.OPEN ||
        !aiSessionIdRef.current
      ) {
        if (microphoneRef.current === microphone) {
          microphoneRef.current = null;
        }
        listeningIntentRef.current = false;
        await microphone.stop().catch(() => {});
        return;
      }
      updateView({
        phase: "listening",
        isListening: true,
        error: null,
        statusMessage: "실키가 잘 듣고 있어요",
        displayText: "",
      });
    } catch (error) {
      microphoneRef.current = null;
      await microphone.stop().catch(() => {});
      throw error;
    }
  }, [updateView]);
  startMicrophoneRef.current = startMicrophone;

  const connect = useCallback(async () => {
    if (!storeId) {
      updateView({
        phase: "error",
        statusMessage: "매장 정보를 확인할 수 없어요",
        error: {
          code: "STORE_ID_MISSING",
          message: "처음 화면으로 돌아가 매장 QR 코드를 다시 인식해주세요.",
          retryable: false,
        },
      });
      return;
    }

    connectionAttemptRef.current += 1;
    const attempt = connectionAttemptRef.current;
    stopRealtimeResources({ sendSessionEnd: true });
    audioStatsRef.current = {
      framesSent: 0,
      bytesSent: 0,
      currentDbfs: null,
      peakDbfs: null,
    };
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    updateView({
      phase: "preparing",
      isListening: false,
      dialog: null,
      error: null,
      audioStats: { ...audioStatsRef.current },
      statusMessage: "안전한 음성 주문 세션을 준비하고 있어요",
    });

    try {
      let orderSession = orderSessionRef.current;

      if (!orderSession && initialOrderSessionId) {
        orderSession = {
          sessionId: initialOrderSessionId,
          storeId,
          cartVersion: 0,
        };
        orderSessionRef.current = orderSession;
        pushDiagnosticEvent("spring.session.resume", "기존 주문 세션 다시 연결");
      }

      if (!orderSession) {
        orderSession = await createOrderSession(storeId, {
          signal: abortController.signal,
        });
        orderSessionRef.current = orderSession;
        pushDiagnosticEvent("spring.session", "주문 세션 생성 완료");
      }

      if (attempt !== connectionAttemptRef.current) {
        return;
      }

      const cart = await getCart(orderSession.sessionId, {
        signal: abortController.signal,
      });
      applyCartSnapshot(cart, { notifyAi: false });
      orderSession = { ...orderSession, cartVersion: cart.cartVersion };
      orderSessionRef.current = orderSession;
      updateView({ orderSessionId: orderSession.sessionId });
      pushDiagnosticEvent(
        "spring.cart",
        `장바구니 v${cart.cartVersion} · ${cart.totalQuantity || 0}개 조회`,
      );

      if (attempt !== connectionAttemptRef.current) {
        return;
      }

      // The token intentionally remains a local variable only. It is never put
      // in React state, a URL, browser storage, or a log.
      const tokenResponse = await issueAiAccessToken(orderSession.sessionId, {
        signal: abortController.signal,
      });
      pushDiagnosticEvent("spring.ai-token", "RS256 단기 토큰 발급 완료");

      if (attempt !== connectionAttemptRef.current) {
        return;
      }

      let accessToken = tokenResponse.accessToken;
      const socket = new WebSocket(getAiWebSocketUrl());
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      let readyWaiter = null;

      socket.addEventListener("message", (event) => {
        if (socketRef.current !== socket) {
          return;
        }

        if (typeof event.data !== "string") {
          return;
        }

        let message;

        try {
          message = JSON.parse(event.data);
        } catch {
          updateView({
            error: {
              code: "MALFORMED_SERVER_MESSAGE",
              message: "AI 서버에서 잘못된 응답을 받았습니다.",
              retryable: true,
            },
          });
          return;
        }

        if (message.type === "session.ready") {
          if (!readyWaiter) {
            expectedCloseSocketsRef.current.add(socket);
            socket.close(1008, "unexpected session.ready");
            return;
          }

          if (
            message.orderSessionId !== orderSession.sessionId ||
            message.storeId !== orderSession.storeId
          ) {
            readyWaiter.reject(new Error("AI 세션의 주문 또는 매장 정보가 일치하지 않습니다."));
            expectedCloseSocketsRef.current.add(socket);
            socket.close(1008, "session binding mismatch");
            return;
          }
          if (!Array.isArray(message.capabilities) || !message.capabilities.includes(DIALOG_CAPABILITY)) {
            readyWaiter.reject(new Error("AI 음성 서버가 대화형 주문 기능을 지원하지 않습니다."));
            expectedCloseSocketsRef.current.add(socket);
            socket.close(1008, "dialog capability missing");
            return;
          }

          aiSessionIdRef.current = message.sessionId;
          pushDiagnosticEvent("session.ready", "JWT와 매장 세션 바인딩 확인 완료");
          readyWaiter.resolve(message);
          return;
        }

        if (
          aiSessionIdRef.current &&
          message.sessionId &&
          message.sessionId !== aiSessionIdRef.current
        ) {
          readyWaiter?.reject(new Error("AI 응답의 세션 정보가 일치하지 않습니다."));
          expectedCloseSocketsRef.current.add(socket);
          socket.close(1008, "response session mismatch");
          const microphone = microphoneRef.current;
          microphoneRef.current = null;
          microphone?.stop().catch(() => {});
          updateView({
            phase: "error",
            isListening: false,
            statusMessage: "AI 응답을 안전하게 확인할 수 없어요",
            error: {
              code: "SESSION_BINDING_MISMATCH",
              message: "AI 응답의 세션 정보가 일치하지 않아 연결을 종료했습니다.",
              retryable: true,
            },
          });
          return;
        }

        if (message.type === "error" && !aiSessionIdRef.current && readyWaiter) {
          const authenticationError = new Error(
            message.message || "AI 음성 세션 인증에 실패했습니다.",
          );
          authenticationError.code = message.code || "AI_AUTHENTICATION_FAILED";
          readyWaiter.reject(authenticationError);
        }

        handleServerMessage(message);
      });

      socket.addEventListener("close", (event) => {
        if (socketRef.current !== socket) {
          return;
        }

        socketRef.current = null;
        aiSessionIdRef.current = null;
        pendingResultTurnIdRef.current = null;
        listeningIntentRef.current = false;
        const microphone = microphoneRef.current;
        microphoneRef.current = null;
        microphone?.stop().catch(() => {});

        if (!expectedCloseSocketsRef.current.has(socket)) {
          readyWaiter?.reject(new Error("AI 음성 서버 연결이 종료되었습니다."));
          clearDialogTimers();
          activeDialogRef.current = null;
          updateView({
            phase: "error",
            isListening: false,
            dialog: null,
            statusMessage: "음성 서버 연결이 종료되었어요",
            error: {
              code: `WS_CLOSED_${event.code}`,
              message: "연결을 다시 시도하면 새 보안 토큰으로 음성 주문을 계속할 수 있어요.",
              retryable: true,
            },
          });
        }
      });

      await waitForSocketOpen(socket);
      pushDiagnosticEvent("ws.open", "AI WebSocket 연결 완료");

      if (attempt !== connectionAttemptRef.current) {
        closeSocket(socket);
        return;
      }

      readyWaiter = createReadyWaiter();
      socket.send(
        JSON.stringify({
          type: "session.start",
          accessToken,
          basedOnCartVersion: orderSession.cartVersion,
          cartItems: toAiCartItems(cart),
          capabilities: [DIALOG_CAPABILITY],
        }),
      );
      pushDiagnosticEvent("session.start", "인증 메시지 전송(토큰은 화면에 저장하지 않음)");
      accessToken = null;
      updateView({ phase: "connecting", statusMessage: "AI 음성 서버에서 인증하고 있어요" });
      await readyWaiter.promise;

      if (attempt !== connectionAttemptRef.current) {
        closeSocket(socket, { sendSessionEnd: true });
        return;
      }

      updateView({ phase: "ready", statusMessage: "마이크를 준비하고 있어요" });
      await startMicrophone();
    } catch (error) {
      if (error?.name === "AbortError" || attempt !== connectionAttemptRef.current) {
        return;
      }

      stopRealtimeResources();
      updateView({
        phase: "error",
        isListening: false,
        statusMessage: "음성 주문을 시작하지 못했어요",
        error: {
          code: error?.code || "VOICE_SESSION_FAILED",
          message: getFriendlyError(error),
          retryable: true,
        },
      });
    }
  }, [
    applyCartSnapshot,
    clearDialogTimers,
    closeSocket,
    handleServerMessage,
    initialOrderSessionId,
    pushDiagnosticEvent,
    startMicrophone,
    stopRealtimeResources,
    storeId,
    updateView,
  ]);

  const toggleListening = useCallback(async () => {
    const microphone = microphoneRef.current;

    if (requiresFreshConnectionRef.current && !microphone?.enabled) {
      pushDiagnosticEvent(
        "connection.refresh",
        "버퍼 턴과 분리하기 위해 새 AI 음성 연결 준비",
      );
      await connect();
      return;
    }

    if (!microphone) {
      if (socketRef.current?.readyState === WebSocket.OPEN && aiSessionIdRef.current) {
        try {
          await startMicrophone();
        } catch (error) {
          updateView({
            phase: "error",
            isListening: false,
            statusMessage: "마이크를 시작하지 못했어요",
            error: {
              code: "MICROPHONE_FAILED",
              message: getFriendlyError(error),
              retryable: true,
            },
          });
        }
      } else {
        await connect();
      }
      return;
    }

    if (microphone.enabled) {
      listeningIntentRef.current = false;
      // Pausing stops PCM frames immediately, so an AI turn that was already
      // speaking/waiting cannot accumulate the silence needed to finish. Use a
      // fresh WebSocket/CLOVA stream on the next start instead of appending the
      // next utterance to that possibly active turn.
      requiresFreshConnectionRef.current = true;
      microphone.pause();
      audioStatsRef.current.currentDbfs = null;
      pushDiagnosticEvent(
        "connection.refresh.pending",
        "수동 일시 중지 후 다음 시작은 새 AI 음성 연결 사용",
      );
      updateView({
        phase: "paused",
        isListening: false,
        audioStats: { ...audioStatsRef.current },
        statusMessage: "음성 인식이 일시 중지되었어요",
      });
    } else {
      listeningIntentRef.current = true;
      ignoredTurnIdsRef.current.clear();
      await microphone.resume();
      updateView({
        phase: "listening",
        isListening: true,
        error: null,
        statusMessage: "실키가 잘 듣고 있어요",
        displayText: "",
      });
    }
  }, [connect, pushDiagnosticEvent, startMicrophone, updateView]);

  const stopDialogPlayback = useCallback(() => {
    clearDialogTimers();
    playerRef.current.stop();
    window.speechSynthesis?.cancel();
    ttsPlaybackIdRef.current += 1;
    listeningIntentRef.current = false;
    microphoneRef.current?.pause();
    updateView({ isListening: false, isPlayingTts: false });
  }, [clearDialogTimers, updateView]);

  const chooseDialogOption = useCallback(
    (choice) => {
      const dialog = activeDialogRef.current;
      if (!dialog || dialog.type !== "clarification" || !choice?.id) return;

      stopDialogPlayback();
      if (dialog.localOnly) {
        const selectedIds = [...(dialog.explicitOptionIds || []), String(choice.value)];
        presentProposal(dialog.proposalMessage, dialog.menu, selectedIds, {
          useRemoteTts: false,
        });
        return;
      }

      if (
        sendDialogControl("dialog.choice", dialog, {
          choiceId: choice.id,
          value: choice.value,
          label: choice.label,
        })
      ) {
        const busy = { ...dialog, isBusy: true };
        activeDialogRef.current = busy;
        updateView({ dialog: busy, phase: "processing", statusMessage: "답변을 확인하고 있어요" });
      }
    },
    [presentProposal, sendDialogControl, stopDialogPlayback, updateView],
  );

  const rejectDialogProposal = useCallback(() => {
    const dialog = activeDialogRef.current;
    if (!dialog || dialog.type !== "proposal" || dialog.isSubmitting) return;
    stopDialogPlayback();
    if (sendDialogControl("dialog.reject", dialog)) {
      const waiting = { ...dialog, isSubmitting: true };
      activeDialogRef.current = waiting;
      updateView({
        dialog: waiting,
        phase: "processing",
        statusMessage: "질문으로 돌아가고 있어요",
        displayText: "원하시는 메뉴를 다시 말씀해주세요.",
      });
    }
  }, [sendDialogControl, stopDialogPlayback, updateView]);

  const acceptDialogProposal = useCallback(async () => {
    const dialog = activeDialogRef.current;
    const orderSession = orderSessionRef.current;
    if (
      !dialog ||
      dialog.type !== "proposal" ||
      dialog.isLoading ||
      dialog.isSubmitting ||
      dialog.error ||
      !orderSession
    ) return;

    if (dialog.basedOnCartVersion !== orderSession.cartVersion) {
      const stale = { ...dialog, error: "장바구니가 변경되어 다시 추천받아야 합니다." };
      setActiveDialog(stale);
      return;
    }

    stopDialogPlayback();
    const submitting = { ...dialog, type: "submitting", isSubmitting: true };
    setActiveDialog(submitting);
    updateView({ phase: "processing", statusMessage: "장바구니에 담고 있어요" });

    try {
      const cart = await addCartItem(orderSession.sessionId, {
        cartVersion: orderSession.cartVersion,
        menuId: dialog.menu.menuId || dialog.menu.id,
        quantity: dialog.quantity,
        optionValueIds: dialog.optionValueIds || [],
      });
      if (!sameDialog(activeDialogRef.current, dialog)) return;
      applyCartSnapshot(cart);
      pushDiagnosticEvent(
        "spring.cart.add",
        `${dialog.menu.name} ${dialog.quantity}개 담기 완료 · v${cart.cartVersion}`,
      );
      const success = {
        ...dialog,
        type: "success",
        menuName: dialog.menu.name,
        text: "장바구니에 담았어요. 더 주문하시겠어요?",
        isSubmitting: false,
        isBusy: true,
      };
      setActiveDialog(success);
      updateView({
        phase: "result",
        statusMessage: "장바구니 반영을 확인하고 있어요",
        displayText: success.text,
      });
    } catch (error) {
      if (error?.code === "CART_VERSION_MISMATCH" && orderSession.sessionId) {
        try {
          applyCartSnapshot(await getCart(orderSession.sessionId));
        } catch {
          // Keep the original add failure visible in the proposal modal.
        }
      }
      if (sameDialog(activeDialogRef.current, dialog)) {
        setActiveDialog({
          ...dialog,
          error: getFriendlyError(error),
          isSubmitting: false,
        });
      }
      updateView({ phase: "error", statusMessage: "장바구니에 담지 못했어요" });
    }
  }, [applyCartSnapshot, pushDiagnosticEvent, setActiveDialog, stopDialogPlayback, updateView]);

  const continueVoiceOrdering = useCallback(() => {
    const dialog = activeDialogRef.current;
    if (!dialog || dialog.type !== "success" || dialog.isBusy) return;
    stopDialogPlayback();
    if (sendDialogControl("dialog.reset", dialog)) {
      const waiting = { ...dialog, isBusy: true };
      activeDialogRef.current = waiting;
      updateView({
        dialog: waiting,
        phase: "processing",
        statusMessage: "새 주문을 준비하고 있어요",
        displayText: "추가로 주문하실 메뉴를 말씀해주세요.",
      });
    }
  }, [sendDialogControl, stopDialogPlayback, updateView]);

  const cancelVoiceDialog = useCallback(() => {
    const dialog = activeDialogRef.current;
    if (!dialog || dialog.type === "submitting" || dialog.isSubmitting) return;

    connectionAttemptRef.current += 1;
    stopRealtimeResources({ sendSessionEnd: true });
    updateView({
      phase: "paused",
      dialog: null,
      isListening: false,
      isPlayingTts: false,
      candidates: [],
      candidateActions: {},
      noMatchMessage: "",
      error: null,
      statusMessage: "음성 주문을 잠시 멈췄어요",
    });
    pushDiagnosticEvent(
      "dialog.cancel",
      "음성 대화를 종료했어요 · 마이크 시작 시 새 연결을 사용합니다",
    );
  }, [pushDiagnosticEvent, stopRealtimeResources, updateView]);

  const selectCandidateOption = useCallback(
    (menuId, groupId, optionValueId) => {
      updateView((current) => {
        const action = current.candidateActions[menuId];
        const group = action?.requiredOptions?.find(
          (item) => String(item.id) === String(groupId),
        );

        if (!action || !group) {
          return {};
        }

        const currentIds = action.selectionByGroup?.[groupId] || [];
        const optionId = String(optionValueId);
        let nextIds;

        if (group.maxSelections === 1) {
          nextIds = [optionId];
        } else if (currentIds.includes(optionId)) {
          nextIds = currentIds.filter((id) => id !== optionId);
        } else if (currentIds.length < group.maxSelections) {
          nextIds = [...currentIds, optionId];
        } else {
          nextIds = currentIds;
        }

        return {
          candidateActions: {
            ...current.candidateActions,
            [menuId]: {
              ...action,
              error: "",
              selectionByGroup: {
                ...action.selectionByGroup,
                [groupId]: nextIds,
              },
            },
          },
        };
      });
    },
    [updateView],
  );

  const addCandidateToCart = useCallback(
    async (candidate) => {
      const menuId = String(candidate?.menuId || "").trim();
      const result = view.lastResult;
      const orderSession = orderSessionRef.current;
      const existingAction = view.candidateActions[menuId];

      if (!menuId || existingAction?.status === "loading" || existingAction?.status === "added") {
        return;
      }

      if (!orderSession || !result) {
        updateView({
          error: {
            code: "ORDER_CONTEXT_MISSING",
            message: "주문 세션 또는 추천 정보를 확인할 수 없습니다. 다시 말씀해주세요.",
            retryable: true,
          },
        });
        return;
      }

      if (result.basedOnCartVersion !== orderSession.cartVersion) {
        updateView((current) => ({
          candidateActions: {
            ...current.candidateActions,
            [menuId]: {
              ...existingAction,
              status: "error",
              error: "장바구니가 변경되었습니다. 새로 추천받은 뒤 담아주세요.",
            },
          },
        }));
        return;
      }

      if (!Number.isInteger(result.quantity) || result.quantity < 1 || result.quantity > 20) {
        updateView((current) => ({
          candidateActions: {
            ...current.candidateActions,
            [menuId]: {
              ...existingAction,
              status: "error",
              error: "한 번에 담을 수 있는 수량은 1개부터 20개까지입니다.",
            },
          },
        }));
        return;
      }

      updateView((current) => ({
        candidateActions: {
          ...current.candidateActions,
          [menuId]: {
            ...existingAction,
            status: "loading",
            error: "",
          },
        },
      }));

      try {
        const menu =
          existingAction?.menu || (await getPublicMenu(storeId, menuId));

        if (String(menu?.id) !== menuId) {
          throw new Error("추천 메뉴와 Spring 메뉴 정보가 일치하지 않습니다.");
        }

        if (menu.salesStatus !== "AVAILABLE") {
          throw new Error("현재 판매 중인 메뉴만 장바구니에 담을 수 있습니다.");
        }

        const optionPlan = getCandidateOptionPlan(
          menu,
          result.attributes,
          existingAction?.selectionByGroup,
        );

        if (optionPlan.requiredOptions.length && existingAction?.status !== "needs-options") {
          updateView((current) => ({
            candidateActions: {
              ...current.candidateActions,
              [menuId]: {
                status: "needs-options",
                error: "",
                menu,
                requiredOptions: optionPlan.requiredOptions,
                selectionByGroup: optionPlan.selectionByGroup,
              },
            },
            statusMessage: "필수 옵션을 확인한 뒤 담아주세요",
          }));
          return;
        }

        const invalidGroup = optionPlan.requiredOptions.find((group) => {
          const selectedCount = optionPlan.selectionByGroup[group.id]?.length || 0;
          return (
            selectedCount < Math.max(1, group.minSelections || 0) ||
            selectedCount > group.maxSelections
          );
        });

        if (invalidGroup) {
          updateView((current) => ({
            candidateActions: {
              ...current.candidateActions,
              [menuId]: {
                ...existingAction,
                status: "needs-options",
                error: `${invalidGroup.name} 옵션을 선택해주세요.`,
                menu,
                requiredOptions: optionPlan.requiredOptions,
                selectionByGroup: optionPlan.selectionByGroup,
              },
            },
          }));
          return;
        }

        const cart = await addCartItem(orderSession.sessionId, {
          cartVersion: orderSession.cartVersion,
          menuId,
          quantity: result.quantity,
          optionValueIds: optionPlan.optionValueIds,
        });
        applyCartSnapshot(cart);
        pushDiagnosticEvent(
          "spring.cart.add",
          `${menu.name} ${result.quantity}개 담기 완료 · v${cart.cartVersion}`,
        );
        updateView((current) => ({
          candidateActions: {
            ...current.candidateActions,
            [menuId]: {
              status: "added",
              error: "",
              menu,
              requiredOptions: optionPlan.requiredOptions,
              selectionByGroup: optionPlan.selectionByGroup,
            },
          },
          statusMessage: `${menu.name} ${result.quantity}개를 장바구니에 담았어요`,
        }));
      } catch (error) {
        if (error?.code === "CART_VERSION_MISMATCH" && orderSession?.sessionId) {
          try {
            const latestCart = await getCart(orderSession.sessionId);
            applyCartSnapshot(latestCart);
          } catch {
            // Preserve the original mutation error; reconnecting will fetch the
            // latest authoritative cart snapshot again.
          }
        }

        updateView((current) => ({
          candidateActions: {
            ...current.candidateActions,
            [menuId]: {
              ...existingAction,
              status: "error",
              error: getFriendlyError(error),
            },
          },
          statusMessage: "장바구니에 담지 못했어요",
        }));
      }
    },
    [
      applyCartSnapshot,
      pushDiagnosticEvent,
      storeId,
      updateView,
      view.candidateActions,
      view.lastResult,
    ],
  );

  const endSession = useCallback(() => {
    connectionAttemptRef.current += 1;
    stopRealtimeResources({ sendSessionEnd: true });
    orderSessionRef.current = null;
    updateView({
      ...INITIAL_VIEW,
      phase: "ended",
      statusMessage: "음성 주문을 종료했어요",
    });
  }, [stopRealtimeResources, updateView]);

  const finishVoiceOrder = useCallback(() => {
    const dialog = activeDialogRef.current;
    const sessionId = orderSessionRef.current?.sessionId;
    if (!dialog || dialog.type !== "success" || dialog.isBusy || !sessionId) return;

    endSession();
    onFinishVoiceOrder?.(sessionId);
  }, [endSession, onFinishVoiceOrder]);

  dialogActionHandlersRef.current = {
    accept: acceptDialogProposal,
    reject: rejectDialogProposal,
    continue: continueVoiceOrdering,
    finish: finishVoiceOrder,
  };

  useEffect(() => {
    mountedRef.current = true;
    void connect();

    return () => {
      mountedRef.current = false;
      connectionAttemptRef.current += 1;
      stopRealtimeResources({ sendSessionEnd: true });
      orderSessionRef.current = null;
    };
  }, [connect, stopRealtimeResources]);

  return {
    ...view,
    acceptDialogProposal,
    addCandidateToCart,
    cancelVoiceDialog,
    chooseDialogOption,
    continueVoiceOrdering,
    finishVoiceOrder,
    replayDialogSpeech,
    rejectDialogProposal,
    selectCandidateOption,
    toggleListening,
    retry: connect,
    endSession,
  };
};
