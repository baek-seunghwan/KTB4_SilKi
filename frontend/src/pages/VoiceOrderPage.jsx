import { useCallback, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { getCartPath, isUuid } from "../api/orders";
import MobileLayout from "../components/layout/MobileLayout";
import UserTopBar from "../components/layout/UserTopBar";
import { useVoiceOrderSession } from "../hooks/useVoiceOrderSession";
const MAGNIFIER_SIZE = 220;
const MAGNIFIER_ZOOM = 1.8;
const USER_TOP_BAR_HEIGHT = 96;

const MicrophoneIcon = ({ isListening }) => (
  <svg
    aria-hidden="true"
    className="size-14"
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M24 30C28.4183 30 32 26.4183 32 22V12C32 7.58172 28.4183 4 24 4C19.5817 4 16 7.58172 16 12V22C16 26.4183 19.5817 30 24 30Z"
      fill="currentColor"
    />
    <path
      d="M10 21C10 28.732 16.268 35 24 35M24 35C31.732 35 38 28.732 38 21M24 35V44M17 44H31"
      stroke="currentColor"
      strokeWidth="4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {!isListening && (
      <path
        d="M8 8L40 40"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    )}
  </svg>
);

const EarIcon = () => (
  <svg
    aria-hidden="true"
    className="size-8 text-primary"
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M34 18C34 11.9249 29.0751 7 23 7C16.9249 7 12 11.9249 12 18M34 18C34 25.5 25 27 25 34C25 37.3137 22.3137 40 19 40C15.6863 40 13 37.3137 13 34M34 18C34 21.866 31.866 24 29 26.5M20 18C20 16.3431 21.3431 15 23 15C24.6569 15 26 16.3431 26 18C26 20.5 23 21.5 23 24"
      stroke="currentColor"
      strokeWidth="4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const getDisplayStatus = ({ error, isListening, phase }) => {
  if (error?.retryable || phase === "preparing" || phase === "connecting") {
    return "실키가 연결을 기다리고 있어요";
  }

  if (isListening) {
    return "실키가 듣고 있어요";
  }

  return "실키가 기다리고 있어요";
};

const InlineDialogActions = ({
  dialog,
  onAccept,
  onChoice,
  onContinue,
  onFinish,
  onReject,
}) => {
  const type = dialog?.type || dialog?.kind;
  let actions = [];

  if (type === "clarification") {
    const choices = Array.isArray(dialog.choices) ? dialog.choices : [];
    actions = choices.map((choice) => ({
      id: choice.id,
      label: choice.label,
      onClick: () => onChoice?.(choice),
      disabled: !onChoice || dialog.isBusy,
    }));
  } else if (type === "proposal" || type === "submitting") {
    const isSubmitting = type === "submitting" || dialog.isSubmitting;
    actions = [
      {
        id: "accept",
        label: "맞아요",
        onClick: onAccept,
        disabled: !onAccept || isSubmitting || dialog.isLoading || Boolean(dialog.error),
      },
      {
        id: "reject",
        label: "아니요",
        onClick: onReject,
        disabled: !onReject || isSubmitting,
      },
    ];
  } else if (type === "success") {
    actions = [
      {
        id: "continue",
        label: "더 주문하기",
        onClick: onContinue,
        disabled: !onContinue || dialog.isBusy,
      },
      {
        id: "finish",
        label: "주문 마치기",
        onClick: onFinish,
        disabled: !onFinish || dialog.isBusy,
      },
    ];
  }

  return (
    <div
      aria-label={actions.length ? "음성 주문 답변 선택" : undefined}
      className="mt-5 flex h-[68px] w-full max-w-2xl items-center overflow-x-auto"
    >
      {dialog?.error ? (
        <p
          role="alert"
          className="w-full rounded-xl bg-error-container px-4 py-3 text-center text-[16px] font-bold text-error"
        >
          {dialog.error}
        </p>
      ) : (
        <div className="flex w-full min-w-max gap-3">
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              onClick={action.onClick}
              disabled={action.disabled}
              className="min-h-14 min-w-[150px] flex-1 rounded-2xl bg-[#5a19de] px-5 py-3 text-[19px] font-extrabold text-white shadow-sm transition active:scale-[0.98] disabled:cursor-wait disabled:bg-surface-variant disabled:text-on-surface-muted"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const VoiceOrderContent = ({
  dialog,
  displayText,
  error,
  isListening,
  isPlayingTts,
  noMatchMessage,
  onAccept,
  onChoice,
  onContinue,
  onFinish,
  onReject,
  onToggleListening,
  phase,
}) => {
  const isConnecting = phase === "preparing" || phase === "connecting";
  const dialogType = dialog?.type || dialog?.kind;
  const requiresButtonResponse =
    dialogType === "proposal" ||
    dialogType === "submitting" ||
    dialogType === "success" ||
    (dialogType === "clarification" && dialog.localOnly);
  const isMicrophoneUnavailable =
    isConnecting || isPlayingTts || phase === "error" || requiresButtonResponse;
  const displayStatus = getDisplayStatus({ error, isListening, phase });

  return (
    <main className="relative flex flex-1 flex-col items-center overflow-y-auto bg-surface-container-lowest px-6 py-8">
      <section className="z-10 w-full max-w-3xl bg-surface-container-lowest text-center">
        <h1 className="text-[34px] font-extrabold leading-[44px] text-on-surface">
          주문하실 메뉴를
          <br />
          말씀해주세요!
        </h1>
        <p className="mt-4 flex items-center justify-center gap-2 text-[22px] font-extrabold leading-8 text-primary">
          <span>{displayStatus}</span>
          <EarIcon />
        </p>
        <div
          aria-live="polite"
          className={`mx-auto mt-8 flex min-h-20 w-full max-w-2xl items-center justify-center rounded-xl border-2 bg-surface-container-lowest p-4 text-[22px] font-semibold leading-8 shadow-sm ${
            isListening
              ? "border-outline text-on-surface-muted"
              : displayText
                ? "border-primary text-on-surface"
              : "border-outline text-on-surface-muted italic"
          }`}
        >
          {displayText ? (
            <p className="min-w-0 break-words text-center not-italic">“{displayText}”</p>
          ) : isListening ? (
            "말씀해주세요. 지금 듣고 있어요"
          ) : (
            "아직 나눈 대화가 없습니다"
          )}
        </div>
      </section>

      <InlineDialogActions
        dialog={dialog}
        onAccept={onAccept}
        onChoice={onChoice}
        onContinue={onContinue}
        onFinish={onFinish}
        onReject={onReject}
      />

      <section className="relative z-10 mt-4 flex size-40 shrink-0 items-center justify-center bg-surface-container-lowest">
        {isListening && (
          <>
            <div className="voice-pulse-ring absolute inset-0 rounded-full bg-primary-container opacity-30" />
            <div className="voice-pulse-ring-delayed absolute inset-0 rounded-full bg-primary-container opacity-30" />
          </>
        )}
        <button
          type="button"
          aria-label={isListening ? "마이크 일시 중지" : "마이크 시작"}
          onClick={onToggleListening}
          disabled={!onToggleListening || isMicrophoneUnavailable}
          className={`relative z-10 flex size-32 items-center justify-center rounded-full shadow-[0_10px_40px_rgba(90,25,222,0.3)] transition-all duration-200 active:scale-95 disabled:cursor-wait disabled:opacity-60 ${
            isListening
              ? "bg-primary text-on-primary"
              : "bg-surface-variant text-on-surface"
          }`}
        >
          <MicrophoneIcon isListening={isListening} />
        </button>
      </section>

      {noMatchMessage && (
        <p
          aria-live="polite"
          className="mt-6 w-full max-w-2xl rounded-2xl bg-surface-container px-5 py-4 text-center text-[18px] font-bold text-on-surface"
        >
          {noMatchMessage}
        </p>
      )}

      {error && !error.retryable && (
        <section
          role="alert"
          className="mt-6 w-full max-w-2xl rounded-2xl border-2 border-error bg-error-container px-5 py-4 text-center"
        >
          <p className="text-[17px] font-bold text-on-surface">{error.message}</p>
        </section>
      )}

      <p className="mt-10 pb-6 text-center text-[28px] font-extrabold leading-10 text-on-surface">
        <span className="block">말씀을 마치시면</span>
        <span className="block">잠시만 기다려주세요!</span>
      </p>
    </main>
  );
};

const VoiceOrderPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const pageRef = useRef(null);
  const routeStoreId =
    typeof location.state?.storeId === "string" ? location.state.storeId.trim() : "";
  const queryStoreId = (searchParams.get("storeId") || "").trim();
  const storeId =
    routeStoreId || queryStoreId || (import.meta.env.VITE_DEFAULT_STORE_ID || "").trim();
  const requestedSessionId = (searchParams.get("sessionId") || "").trim();
  const existingSessionId = isUuid(requestedSessionId) ? requestedSessionId : "";
  const handleVoiceOrderFinished = useCallback(
    (sessionId) => {
      const cartPath = getCartPath(storeId, sessionId);
      if (cartPath) navigate(cartPath);
    },
    [navigate, storeId],
  );
  const voiceSession = useVoiceOrderSession(
    storeId,
    existingSessionId,
    handleVoiceOrderFinished,
  );
  const [isMagnifierActive, setIsMagnifierActive] = useState(false);
  const [isDraggingMagnifier, setIsDraggingMagnifier] = useState(false);
  const [magnifierPosition, setMagnifierPosition] = useState({ x: 240, y: 360 });
  const [pageSize, setPageSize] = useState({ width: 480, height: 740 });

  const updateMagnifierPosition = (event) => {
    const page = pageRef.current;

    if (!page) {
      return;
    }

    const bounds = page.getBoundingClientRect();
    setPageSize({ width: bounds.width, height: bounds.height });
    const radius = MAGNIFIER_SIZE / 2;
    const nextX = Math.min(
      Math.max(event.clientX - bounds.left, radius),
      bounds.width - radius,
    );
    const nextY = Math.min(
      Math.max(event.clientY - bounds.top, USER_TOP_BAR_HEIGHT + radius),
      bounds.height - radius,
    );

    setMagnifierPosition({ x: nextX, y: nextY });
  };

  const handleMagnifierPointerDown = (event) => {
    setIsDraggingMagnifier(true);
    updateMagnifierPosition(event);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleMagnifierPointerMove = (event) => {
    if (isDraggingMagnifier) {
      updateMagnifierPosition(event);
    }
  };

  const handleMagnifierPointerUp = () => {
    setIsDraggingMagnifier(false);
  };

  const toggleMagnifier = () => {
    const bounds = pageRef.current?.getBoundingClientRect();

    if (bounds) {
      setPageSize({ width: bounds.width, height: bounds.height });
    }

    setIsMagnifierActive((current) => !current);
  };

  const voiceContentProps = {
    dialog: voiceSession.dialog,
    displayText: voiceSession.displayText,
    error: voiceSession.error,
    isListening: voiceSession.isListening,
    isPlayingTts: voiceSession.isPlayingTts,
    noMatchMessage: voiceSession.noMatchMessage,
    phase: voiceSession.phase,
  };

  return (
    <MobileLayout
      surfaceClassName="customer-page bg-surface-container-lowest"
      contentClassName="relative flex min-h-[inherit] w-full flex-col overflow-hidden bg-surface-container-lowest px-0 py-0 text-on-surface"
    >
      <div
        ref={pageRef}
        className="relative flex min-h-[inherit] w-full flex-col bg-surface-container-lowest"
      >
        <div data-voice-order-background className="flex min-h-[inherit] w-full flex-col bg-surface-container-lowest">
          <UserTopBar
            actionLabel="돋보기"
            onActionClick={toggleMagnifier}
          />

          <VoiceOrderContent
            {...voiceContentProps}
            onAccept={voiceSession.acceptDialogProposal}
            onChoice={voiceSession.chooseDialogOption}
            onContinue={voiceSession.continueVoiceOrdering}
            onFinish={voiceSession.finishVoiceOrder}
            onReject={voiceSession.rejectDialogProposal}
            onToggleListening={voiceSession.toggleListening}
          />

          {isMagnifierActive && (
            <>
              <button
                type="button"
                onClick={() => setIsMagnifierActive(false)}
                className="absolute bottom-8 left-1/2 z-[70] flex w-[320px] max-w-[calc(100%-48px)] -translate-x-1/2 items-center justify-center rounded-2xl bg-error px-6 py-6 text-[24px] font-extrabold text-white shadow-[0_14px_30px_rgba(239,68,68,0.28)] transition-transform duration-150 active:scale-95"
              >
                돋보기 끄기
              </button>

              <div
                role="presentation"
                className="absolute inset-x-0 bottom-0 top-24 z-[60] cursor-grab touch-none active:cursor-grabbing"
                onPointerDown={handleMagnifierPointerDown}
                onPointerMove={handleMagnifierPointerMove}
                onPointerUp={handleMagnifierPointerUp}
                onPointerCancel={handleMagnifierPointerUp}
              >
                <div
                  className="pointer-events-none absolute overflow-hidden rounded-full border-4 border-primary bg-surface-container-lowest shadow-[0_18px_40px_rgba(27,27,30,0.28)]"
                  style={{
                    left: magnifierPosition.x - MAGNIFIER_SIZE / 2,
                    top: magnifierPosition.y - USER_TOP_BAR_HEIGHT - MAGNIFIER_SIZE / 2,
                    width: MAGNIFIER_SIZE,
                    height: MAGNIFIER_SIZE,
                  }}
                >
                  <div
                    aria-hidden="true"
                    className="absolute left-0 top-0 flex min-h-full w-full flex-col bg-surface-container-lowest text-on-surface"
                    style={{
                      width: pageSize.width,
                      height: pageSize.height,
                      transform: `translate(${MAGNIFIER_SIZE / 2 - magnifierPosition.x * MAGNIFIER_ZOOM}px, ${MAGNIFIER_SIZE / 2 - magnifierPosition.y * MAGNIFIER_ZOOM}px) scale(${MAGNIFIER_ZOOM})`,
                      transformOrigin: "top left",
                    }}
                  >
                    <UserTopBar actionLabel="돋보기" />
                    <VoiceOrderContent {...voiceContentProps} />
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

      </div>
    </MobileLayout>
  );
};

export default VoiceOrderPage;
