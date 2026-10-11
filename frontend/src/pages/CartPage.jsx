import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  checkoutOrder,
  deleteCartItem,
  getCart,
  isUuid,
  selectFulfillment,
  updateCartItem,
} from "../api/orders";
import MobileLayout from "../components/layout/MobileLayout";
import UserTopBar from "../components/layout/UserTopBar";
import MagnifierOffButton from "../components/common/MagnifierOffButton";

const MAGNIFIER_SIZE = 220;
const MAGNIFIER_ZOOM = 1.8;
const USER_TOP_BAR_HEIGHT = 96;
const CART_FOOTER_HEIGHT = 280;
const CART_MAGNIFIER_TOP_OFFSET = -96;
const formatPrice = (price = 0) => `${Number(price).toLocaleString("ko-KR")}원`;

const PlusIcon = () => (
  <svg aria-hidden="true" className="size-6" viewBox="0 0 24 24" fill="none">
    <path d="M12 5V19M5 12H19" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

const CartBasketIcon = () => (
  <svg aria-hidden="true" className="size-9 text-primary" viewBox="0 0 32 32" fill="none">
    <path d="M9 12L13 5M23 12L19 5" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <path d="M5 12H27L25 26H7L5 12Z" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" />
    <path d="M12 17V22M20 17V22" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

const CreditCardIcon = () => (
  <svg aria-hidden="true" className="size-10" viewBox="0 0 32 32" fill="none">
    <rect x="4" y="8" width="24" height="16" rx="3" stroke="currentColor" strokeWidth="3" />
    <path d="M4 14H28M9 20H14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

const CartItemCard = ({ busy, item, onDecrease, onIncrease }) => (
  <article className="rounded-2xl border-2 border-outline-variant bg-surface-container-low p-4">
    <div className="flex min-w-0 items-start gap-4">
      {item.imageUrl ? (
        <img alt="" className="h-20 w-20 shrink-0 rounded-xl object-cover shadow-sm" src={item.imageUrl} />
      ) : (
        <div className="h-20 w-20 shrink-0 rounded-xl bg-gradient-to-br from-primary-fixed to-surface-container-high shadow-sm" />
      )}
      <div className="min-w-0 flex-1">
        <h3 className="mb-2 break-words text-[24px] font-extrabold leading-8 text-on-surface">{item.menuName}</h3>
        <div className="flex flex-wrap gap-2">
          {item.options.map((option) => (
            <span key={option.optionValueId} className="rounded-lg bg-surface-container-highest px-3 py-1.5 text-[16px] font-bold leading-5 text-on-surface-variant">
              {option.name}
            </span>
          ))}
        </div>
        {!item.available && <p className="mt-1 text-label-lg font-bold text-error">현재 품절된 메뉴예요</p>}
      </div>
    </div>
    <div className="mt-4 border-t-2 border-outline-variant pt-4">
      <p className="mb-3 text-[24px] font-extrabold leading-8 text-secondary">{formatPrice(item.totalPrice)}</p>
      <div className="grid w-full grid-cols-[1fr_52px_1fr] items-center gap-2 rounded-2xl border border-outline-variant bg-surface p-1.5">
        <button aria-label="수량 감소" className="flex min-h-12 items-center justify-center rounded-xl bg-surface-container-high px-3 text-[19px] font-extrabold disabled:opacity-40" disabled={busy} type="button" onClick={onDecrease}>빼기</button>
        <span className="text-center text-[24px] font-extrabold" aria-label={`수량 ${item.quantity}개`}>{item.quantity}</span>
        <button aria-label="수량 증가" className="flex min-h-12 items-center justify-center rounded-xl bg-primary px-3 text-[19px] font-extrabold text-on-primary disabled:opacity-40" disabled={busy || item.quantity >= 20} type="button" onClick={onIncrease}>더하기</button>
      </div>
    </div>
  </article>
);

const CartContent = ({ busy, items, onDecreaseQuantity, onIncreaseQuantity, voiceOrderPath }) => (
  <main className="flex-1 overflow-y-auto bg-surface px-4 pb-[300px] pt-8">
    <div className="mb-8 flex flex-col gap-4">
      <h1 className="flex items-center gap-2 text-[30px] font-extrabold leading-10 text-on-surface">
        <span><span className="text-primary">장바구니</span>를 확인해요</span>
        <CartBasketIcon />
      </h1>
      <div className="flex justify-end">
        <Link className="flex items-center gap-1 rounded-xl bg-primary-fixed px-4 py-3 text-[22px] font-extrabold leading-7 text-primary" to={voiceOrderPath}>
          <PlusIcon /> 추가 주문
        </Link>
      </div>
    </div>
    <div className="mt-6 space-y-4">
      {items.length === 0 && <p className="rounded-2xl bg-surface-container-low p-8 text-center text-[22px] font-bold text-on-surface-variant">장바구니가 비어 있어요.</p>}
      {items.map((item) => (
        <CartItemCard
          key={item.cartItemId}
          busy={busy}
          item={item}
          onDecrease={() => onDecreaseQuantity(item)}
          onIncrease={() => onIncreaseQuantity(item)}
        />
      ))}
    </div>
  </main>
);

const CartFooter = ({ busy, disabled, fulfillmentType, onCheckout, onFulfillmentChange, totalPrice }) => (
  <footer className="absolute inset-x-0 bottom-0 z-50 rounded-t-3xl border-t-2 border-outline-variant bg-surface-container-low p-4 shadow-[0_-5px_20px_-10px_rgba(0,0,0,0.1)]">
    <fieldset className="mb-3 grid grid-cols-2 gap-2">
      <legend className="sr-only">이용 방법</legend>
      {[["DINE_IN", "매장에서 먹기"], ["TAKEOUT", "포장하기"]].map(([value, label]) => (
        <label key={value} className={`flex h-12 cursor-pointer items-center justify-center rounded-xl border-2 text-[18px] font-bold ${fulfillmentType === value ? "border-primary bg-primary-fixed text-primary" : "border-outline-variant bg-surface-container-lowest text-on-surface"}`}>
          <input checked={fulfillmentType === value} className="sr-only" disabled={busy} name="fulfillmentType" type="radio" value={value} onChange={() => onFulfillmentChange(value)} />
          {label}
        </label>
      ))}
    </fieldset>
    <div className="mb-3 flex items-center justify-between px-2">
      <span className="text-[24px] font-bold text-on-surface">총 결제 금액</span>
      <span className="text-[32px] font-extrabold text-primary">{formatPrice(totalPrice)}</span>
    </div>
    <button className="flex min-h-16 w-full items-center justify-center gap-4 rounded-2xl bg-primary-container text-[30px] font-bold text-on-primary shadow-lg disabled:opacity-40" disabled={disabled || busy} type="button" onClick={onCheckout}>
      <CreditCardIcon /> {busy ? "처리 중..." : "주문하기"}
    </button>
  </footer>
);

const CartPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const storeId = searchParams.get("storeId");
  const sessionId = searchParams.get("sessionId");
  const hasValidContext = isUuid(storeId) && isUuid(sessionId);
  const pageRef = useRef(null);
  const checkoutKeyRef = useRef(crypto.randomUUID());
  const [cart, setCart] = useState(null);
  const [error, setError] = useState(hasValidContext ? "" : "주문 정보를 확인할 수 없어요.");
  const [busy, setBusy] = useState(hasValidContext);
  const [isMagnifierActive, setIsMagnifierActive] = useState(false);
  const [isDraggingMagnifier, setIsDraggingMagnifier] = useState(false);
  const [magnifierPosition, setMagnifierPosition] = useState({ x: 240, y: 300 });
  const voiceOrderPath = `/voice-order?${new URLSearchParams({ storeId: storeId || "", sessionId: sessionId || "" })}`;

  const refreshCart = async () => {
    if (!hasValidContext) return;
    setCart(await getCart(sessionId));
  };

  useEffect(() => {
    let active = true;
    if (!hasValidContext) return undefined;
    getCart(sessionId)
      .then((current) => { if (active) { setCart(current); setError(""); } })
      .catch((requestError) => { if (active) setError(requestError.message); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [hasValidContext, sessionId]);

  const runCartMutation = async (mutation) => {
    if (!cart || busy) return;
    setBusy(true);
    setError("");
    try {
      setCart(await mutation());
    } catch (requestError) {
      if (requestError.code === "CART_VERSION_MISMATCH") await refreshCart().catch(() => {});
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const handleQuantity = (item, quantity) => runCartMutation(() => quantity === 0
    ? deleteCartItem(sessionId, item.cartItemId, cart.cartVersion)
    : updateCartItem(
      sessionId,
      item.cartItemId,
      cart.cartVersion,
      quantity,
      item.options.map(({ optionValueId }) => optionValueId),
    ));

  const handleFulfillment = (fulfillmentType) => runCartMutation(async () => {
    const updated = await selectFulfillment(sessionId, cart.cartVersion, fulfillmentType);
    return { ...cart, ...updated };
  });

  const handleCheckout = async () => {
    if (!cart || busy) return;
    setBusy(true);
    setError("");
    try {
      const order = await checkoutOrder(sessionId, cart.cartVersion, checkoutKeyRef.current);
      navigate(`/order-status/${order.id}`, { replace: true, state: { order } });
    } catch (requestError) {
      if (requestError.code === "CART_VERSION_MISMATCH") await refreshCart().catch(() => {});
      setError(requestError.message);
      setBusy(false);
    }
  };

  const updateMagnifierPosition = (event) => {
    const bounds = pageRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const radius = MAGNIFIER_SIZE / 2;
    setMagnifierPosition({
      x: Math.min(Math.max(event.clientX - bounds.left, radius), bounds.width - radius),
      y: Math.min(
        Math.max(event.clientY - bounds.top, USER_TOP_BAR_HEIGHT + CART_MAGNIFIER_TOP_OFFSET + radius),
        bounds.height - CART_FOOTER_HEIGHT - radius,
      ),
    });
  };

  const handleMagnifierPointerDown = (event) => {
    setIsDraggingMagnifier(true);
    updateMagnifierPosition(event);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  if (!hasValidContext) {
    return <MobileLayout surfaceClassName="customer-page bg-surface"><main className="flex min-h-[inherit] flex-col items-center justify-center px-6 text-center"><p className="text-[26px] font-bold">{error}</p><Link className="mt-6 rounded-xl bg-primary-container px-6 py-3 text-white" to="/qr-scan">다시 스캔하기</Link></main></MobileLayout>;
  }

  const content = cart ? (
    <CartContent
      busy={busy}
      items={cart.items}
      voiceOrderPath={voiceOrderPath}
      onDecreaseQuantity={(item) => handleQuantity(item, item.quantity - 1)}
      onIncreaseQuantity={(item) => handleQuantity(item, item.quantity + 1)}
    />
  ) : <main className="flex flex-1 items-center justify-center text-[22px] font-bold">장바구니를 불러오고 있어요...</main>;

  return (
    <MobileLayout surfaceClassName="customer-page bg-surface" contentClassName="relative flex min-h-[inherit] w-full flex-col overflow-hidden bg-surface px-0 py-0 text-on-surface">
      <div ref={pageRef} className="relative flex min-h-[inherit] w-full flex-col bg-surface">
        <UserTopBar actionLabel="돋보기" onActionClick={() => setIsMagnifierActive((current) => !current)} />
        {content}
        {error && <p className="absolute inset-x-4 bottom-[286px] z-50 rounded-xl bg-error-container p-3 text-center font-bold text-error" role="alert">{error}</p>}
        {cart && (
          <CartFooter
            busy={busy}
            disabled={cart.items.length === 0 || !cart.fulfillmentType || cart.items.some(({ available }) => !available)}
            fulfillmentType={cart.fulfillmentType}
            totalPrice={cart.totalPrice}
            onCheckout={handleCheckout}
            onFulfillmentChange={handleFulfillment}
          />
        )}
        {isMagnifierActive && cart && (
          <>
            <MagnifierOffButton className="absolute bottom-[202px] left-1/2 z-[70] -translate-x-1/2" onClick={() => setIsMagnifierActive(false)} />
            <div role="presentation" className="absolute inset-x-0 bottom-[280px] top-0 z-[60] cursor-grab touch-none active:cursor-grabbing" onPointerDown={handleMagnifierPointerDown} onPointerMove={(event) => isDraggingMagnifier && updateMagnifierPosition(event)} onPointerUp={() => setIsDraggingMagnifier(false)} onPointerCancel={() => setIsDraggingMagnifier(false)}>
              <div className="pointer-events-none absolute overflow-hidden rounded-full border-4 border-primary bg-surface-container-lowest shadow-[0_18px_40px_rgba(27,27,30,0.28)]" style={{ left: magnifierPosition.x - MAGNIFIER_SIZE / 2, top: magnifierPosition.y - USER_TOP_BAR_HEIGHT - CART_MAGNIFIER_TOP_OFFSET - MAGNIFIER_SIZE / 2, width: MAGNIFIER_SIZE, height: MAGNIFIER_SIZE }}>
                <div aria-hidden="true" className="absolute left-0 top-0 flex min-h-full w-full flex-col bg-surface text-on-surface" style={{ width: 480, height: 740, transform: `translate(${MAGNIFIER_SIZE / 2 - magnifierPosition.x * MAGNIFIER_ZOOM}px, ${MAGNIFIER_SIZE / 2 - magnifierPosition.y * MAGNIFIER_ZOOM}px) scale(${MAGNIFIER_ZOOM})`, transformOrigin: "top left" }}>
                  <UserTopBar actionLabel="돋보기" />
                  <CartContent busy items={cart.items} voiceOrderPath={voiceOrderPath} onDecreaseQuantity={() => {}} onIncreaseQuantity={() => {}} />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </MobileLayout>
  );
};

export default CartPage;
