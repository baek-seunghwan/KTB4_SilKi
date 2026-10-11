import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { getOrder, isUuid, mergeOrder, subscribeToOrderStatus } from "../api/orders";
import MobileLayout from "../components/layout/MobileLayout";
import UserTopBar from "../components/layout/UserTopBar";
import MagnifierOffButton from "../components/common/MagnifierOffButton";

const MAGNIFIER_SIZE = 220;
const MAGNIFIER_ZOOM = 1.8;

const CookingIcon = ({ status }) => (
  <svg aria-hidden="true" className="size-12" viewBox="0 0 48 48" fill="none">
    <path
      d="M14 21H34L32 39H16L14 21Z"
      stroke="currentColor"
      strokeWidth="4"
      strokeLinejoin="round"
    />
    <path
      d="M18 21V17C18 13.6863 20.6863 11 24 11C27.3137 11 30 13.6863 30 17V21M13 21H35"
      stroke="currentColor"
      strokeWidth="4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      className={status === "PREPARING" ? "order-cooking-steam" : ""}
      d="M18 7C18 5.5 19 4 21 4M24 7C24 5.5 25 4 27 4M30 7C30 5.5 31 4 33 4"
      stroke="currentColor"
      strokeWidth="4"
      strokeLinecap="round"
    />
  </svg>
);

const ChevronDownIcon = ({ isOpen }) => (
  <svg
    aria-hidden="true"
    className={`size-10 text-primary-container transition-transform duration-300 ${
      isOpen ? "rotate-180" : ""
    }`}
    viewBox="0 0 24 24"
    fill="none"
  >
    <path
      d="M6 9L12 15L18 9"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const statusLabels = {
  RECEIVED: "주문 완료",
  PREPARING: "조리 중",
  COMPLETED: "조리 완료",
};
const progressSteps = Object.entries(statusLabels);
const formatPrice = (price) => `${Number(price).toLocaleString("ko-KR")}원`;
const fireworks = [
  { delay: 0, left: "28%", top: "30%", rise: "-470px" },
  { delay: 420, left: "70%", top: "23%", rise: "-525px" },
  { delay: 950, left: "50%", top: "38%", rise: "-410px" },
];
const confettiPieces = Array.from({ length: 20 }, (_, index) => {
  const angle = (index / 20) * Math.PI * 2 - Math.PI / 2;
  const radius = 105 + (index % 3) * 22;
  return {
    color: ["#5a19de", "#60a5fa", "#5eead4", "#f9a8d4", "#fde68a"][index % 5],
    delay: `${720 + (index % 4) * 25}ms`,
    rotation: `${180 + (index % 5) * 90}deg`,
    x: `${Math.cos(angle) * radius}px`,
    y: `${Math.sin(angle) * radius}px`,
  };
});

const Confetti = () => (
  <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-[80] overflow-hidden">
    {fireworks.map((firework, fireworkIndex) => (
      <span
        className="order-firework"
        key={firework.left}
        style={{
          "--firework-delay": `${firework.delay}ms`,
          "--firework-left": firework.left,
          "--firework-rise": firework.rise,
          "--firework-top": firework.top,
        }}
      >
        <span className="order-firework-launch"><i /><i /><i /></span>
        {confettiPieces.map((piece, pieceIndex) => (
          <span
            className="order-confetti-piece"
            key={`${fireworkIndex}-${pieceIndex}`}
            style={{
              "--confetti-color": piece.color,
              "--confetti-delay": piece.delay,
              "--confetti-rotation": piece.rotation,
              "--confetti-x": piece.x,
              "--confetti-y": piece.y,
            }}
          />
        ))}
      </span>
    ))}
  </div>
);

const OrderProgress = ({ status }) => {
  const currentIndex = Math.max(0, progressSteps.findIndex(([value]) => value === status));

  return (
    <div
      aria-label="조리 진행도"
      aria-valuemax={3}
      aria-valuemin={1}
      aria-valuenow={currentIndex + 1}
      className="mx-auto mt-10 w-full max-w-xl"
      role="progressbar"
    >
      <div className="relative">
        <div className="absolute left-[16.67%] right-[16.67%] top-6 h-2 rounded-full bg-surface-container-highest" />
        <div
          className="order-progress-track absolute left-[16.67%] top-6 h-2 rounded-full transition-[width] duration-700"
          style={{ width: `${currentIndex * 33.33}%` }}
        />
        <ol className="relative flex justify-between">
          {progressSteps.map(([value, label], index) => {
            const reached = index <= currentIndex;
            return (
              <li className="flex w-1/3 flex-col items-center" key={value}>
                <span
                  aria-current={index === currentIndex ? "step" : undefined}
                  className={`order-progress-dot order-progress-${value.toLowerCase()} flex size-14 items-center justify-center rounded-full border-4 text-[22px] font-extrabold transition-all duration-500 ${reached ? "is-reached" : ""} ${index === currentIndex ? "is-current" : ""}`}
                >
                  {reached ? "✓" : index + 1}
                </span>
                <span className={`order-progress-label order-progress-${value.toLowerCase()} mt-3 rounded-full px-3 py-1 text-[18px] font-bold ${reached ? "is-reached" : ""}`}>
                  {label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
};

const OrderStatusContent = ({ isDetailsOpen, onToggleDetails, order }) => {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center overflow-hidden px-6 py-8">
      <section className="shrink-0 pt-16 text-center">
        <h1 className="mb-6 text-[48px] font-extrabold leading-[60px] text-on-background">
          주문번호 {order.orderNumber}번
        </h1>
        <p className="mb-8 rounded-2xl bg-primary-fixed px-6 py-4 text-[26px] font-extrabold leading-9 text-primary shadow-sm">
          결제는 직원에게 직접해주세요!
        </p>
        <div className={`order-status-badge order-status-${order.status.toLowerCase()} relative inline-flex items-center justify-center rounded-full bg-primary-container px-12 py-6 text-[36px] font-bold leading-[44px] text-on-primary shadow-lg`}>
          {order.status === "COMPLETED" && (
            <span aria-hidden="true" className="order-complete-sparkles">
              <i>✦</i><i>✦</i><i>✦</i><i>✦</i><i>✦</i><i>✦</i>
            </span>
          )}
          <CookingIcon status={order.status} />
          <span className="ml-4">{statusLabels[order.status] || order.status}</span>
        </div>
        <OrderProgress status={order.status} />
      </section>

      <section className="mt-8 flex max-h-[360px] w-full max-w-2xl shrink-0 flex-col overflow-hidden rounded-xl border-2 border-outline-variant bg-surface-variant">
        <button
          type="button"
          onClick={onToggleDetails}
          className="flex h-[100px] w-full shrink-0 items-center justify-between bg-surface-container-high p-8 transition-transform duration-150 active:scale-95"
        >
          <span className="text-[28px] font-bold leading-9 text-on-background">
            주문 내역
          </span>
          <ChevronDownIcon isOpen={isDetailsOpen} />
        </button>

        {isDetailsOpen && (
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto bg-surface-container-lowest p-8">
            {order.items.length === 0 && (
              <p className="py-6 text-center text-body-lg text-on-surface-variant">주문 상세 내역이 없어요.</p>
            )}
            {order.items.map((item, index) => (
              <div
                key={`${item.menuName}-${index}`}
                className="border-b border-outline-variant py-4"
              >
                <div className="w-full">
                  <span className="text-[24px] font-medium leading-8 text-on-background">
                    {item.menuName}
                  </span>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(item.options || []).map((option) => (
                        <span
                          key={`${option.type}-${option.code}`}
                          className="inline-block whitespace-nowrap rounded-lg bg-surface-container-highest px-3 py-1 text-[12px] font-bold leading-5 text-on-surface-variant"
                        >
                          {option.name}
                        </span>
                    ))}
                  </div>
                  <p className="mt-4 text-right text-[24px] font-bold leading-8 text-primary-container">
                    {formatPrice(item.unitPrice)}
                    {item.quantity > 1 && ` × ${item.quantity}`}
                  </p>
                </div>
              </div>
            ))}

            <div className="mt-4 flex items-center justify-between pt-6">
              <span className="text-[28px] font-bold leading-9 text-on-background">
                총 결제 금액
              </span>
              <span className="text-[32px] font-extrabold leading-10 text-primary">
                {order.totalPrice == null ? "-" : formatPrice(order.totalPrice)}
              </span>
            </div>
          </div>
        )}
      </section>
    </main>
  );
};

const OrderStatusPage = () => {
  const { orderId } = useParams();
  const location = useLocation();
  const hasValidOrderId = isUuid(orderId);
  const initialOrder = location.state?.order?.id === orderId ? location.state.order : null;
  const pageRef = useRef(null);
  const statusRef = useRef(initialOrder?.status);
  const confettiTimeoutRef = useRef(null);
  const [order, setOrder] = useState(initialOrder);
  const [showConfetti, setShowConfetti] = useState(false);
  const [isLoading, setIsLoading] = useState(hasValidOrderId && !initialOrder);
  const [loadError, setLoadError] = useState(hasValidOrderId ? "" : "주문을 찾을 수 없어요.");
  const [retryCount, setRetryCount] = useState(0);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isMagnifierActive, setIsMagnifierActive] = useState(false);
  const [isDraggingMagnifier, setIsDraggingMagnifier] = useState(false);
  const [magnifierPosition, setMagnifierPosition] = useState({ x: 240, y: 360 });

  const celebrateCompletion = useCallback((nextStatus) => {
    if (statusRef.current && statusRef.current !== "COMPLETED" && nextStatus === "COMPLETED") {
      setShowConfetti(true);
      window.clearTimeout(confettiTimeoutRef.current);
      confettiTimeoutRef.current = window.setTimeout(() => setShowConfetti(false), 3400);
    }
    statusRef.current = nextStatus;
  }, []);

  useEffect(() => {
    let active = true;
    let unsubscribe;

    if (!hasValidOrderId) return undefined;

    const refresh = async () => {
      try {
        const current = await getOrder(orderId);
        if (active) {
          celebrateCompletion(current.status);
          setOrder((previous) => mergeOrder(previous, current));
          setLoadError("");
          if (current.status === "COMPLETED") unsubscribe?.();
        }
      } catch (error) {
        if (active) {
          setLoadError(error.status === 404
            ? "주문을 찾을 수 없어요."
            : "주문을 불러오지 못했어요.");
          if (error.status === 404) unsubscribe?.();
        }
      } finally {
        if (active) setIsLoading(false);
      }
    };

    unsubscribe = subscribeToOrderStatus(orderId, (status) => {
      if (!active) return;
      celebrateCompletion(status.status);
      setOrder((current) => mergeOrder(current, status));
      if (status.status === "COMPLETED") unsubscribe?.();
    }, refresh);
    refresh();

    return () => {
      active = false;
      unsubscribe?.();
      window.clearTimeout(confettiTimeoutRef.current);
    };
  }, [celebrateCompletion, hasValidOrderId, orderId, retryCount]);

  const updateMagnifierPosition = (event) => {
    const page = pageRef.current;

    if (!page) {
      return;
    }

    const bounds = page.getBoundingClientRect();
    const radius = MAGNIFIER_SIZE / 2;
    const nextX = Math.min(
      Math.max(event.clientX - bounds.left, radius),
      bounds.width - radius,
    );
    const nextY = Math.min(
      Math.max(event.clientY - bounds.top, radius),
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

  return (
    <MobileLayout
      surfaceClassName="customer-page bg-surface-container-lowest"
      contentClassName="relative flex min-h-[inherit] w-full flex-col overflow-hidden bg-surface-container-lowest px-0 py-0 text-on-background"
    >
      <div
        ref={pageRef}
        className="relative flex min-h-[inherit] w-full flex-col bg-surface-container-lowest"
      >
        <UserTopBar
          actionLabel="돋보기"
          onActionClick={() => setIsMagnifierActive((current) => !current)}
        />

        {showConfetti && <Confetti />}

        {order ? (
          <>
            {loadError && <p className="px-6 pt-4 text-center text-error" role="alert">{loadError}</p>}
            <OrderStatusContent
              order={order}
              isDetailsOpen={isDetailsOpen}
              onToggleDetails={() => setIsDetailsOpen((current) => !current)}
            />
          </>
        ) : (
          <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <p className="text-[26px] font-bold text-on-surface" role={loadError ? "alert" : "status"}>
              {isLoading ? "주문을 불러오고 있어요..." : loadError}
            </p>
            {!isLoading && loadError && loadError !== "주문을 찾을 수 없어요." && (
              <button className="mt-6 rounded-xl bg-primary-container px-6 py-3 text-[20px] font-bold text-white" type="button" onClick={() => { setIsLoading(true); setRetryCount((count) => count + 1); }}>
                다시 시도
              </button>
            )}
          </main>
        )}

        {order && isMagnifierActive && (
          <>
            <MagnifierOffButton
              onClick={() => setIsMagnifierActive(false)}
              className="absolute bottom-8 left-1/2 z-[70] -translate-x-1/2"
            />

            <div
              role="presentation"
              className="absolute inset-0 z-[60] cursor-grab touch-none active:cursor-grabbing"
              onPointerDown={handleMagnifierPointerDown}
              onPointerMove={handleMagnifierPointerMove}
              onPointerUp={handleMagnifierPointerUp}
              onPointerCancel={handleMagnifierPointerUp}
            >
              <div
                className="pointer-events-none absolute overflow-hidden rounded-full border-4 border-primary bg-surface-container-lowest shadow-[0_18px_40px_rgba(27,27,30,0.28)]"
                style={{
                  left: magnifierPosition.x - MAGNIFIER_SIZE / 2,
                  top: magnifierPosition.y - MAGNIFIER_SIZE / 2,
                  width: MAGNIFIER_SIZE,
                  height: MAGNIFIER_SIZE,
                }}
              >
                <div
                  aria-hidden="true"
                  className="absolute left-0 top-0 flex min-h-full w-full flex-col bg-surface-container-lowest text-on-background"
                  style={{
                    width: 480,
                    height: 740,
                    transform: `translate(${
                      MAGNIFIER_SIZE / 2 - magnifierPosition.x * MAGNIFIER_ZOOM
                    }px, ${
                      MAGNIFIER_SIZE / 2 - magnifierPosition.y * MAGNIFIER_ZOOM
                    }px) scale(${MAGNIFIER_ZOOM})`,
                    transformOrigin: "top left",
                  }}
                >
                  <UserTopBar actionLabel="돋보기" />
                  <OrderStatusContent
                    order={order}
                    isDetailsOpen={isDetailsOpen}
                    onToggleDetails={() => {}}
                  />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </MobileLayout>
  );
};

export default OrderStatusPage;
