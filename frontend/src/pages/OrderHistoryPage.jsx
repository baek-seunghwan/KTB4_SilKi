import { useEffect, useState } from "react";
import { getAdminSession } from "../api/client";
import { filterOrdersByStatus, getOrders, sortOrders, subscribeToOrders, updateOrderStatus, updateVisibleOrders } from "../api/orders";
import { CheckCircleIcon, OrdersIcon } from "../components/icons";
import AdminLayout from "../components/layout/AdminLayout";

const filters = [
  { label: "진행 중인 주문", value: "active", statuses: ["RECEIVED", "PREPARING"] },
  { label: "완료된 주문", value: "completed", statuses: ["COMPLETED"] },
];
const statusLabels = { RECEIVED: "접수", PREPARING: "조리 중", COMPLETED: "완료" };

const formatDate = (value) => new Intl.DateTimeFormat("ko-KR", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
}).format(new Date(value));

const OrderCard = ({ busy, onStatusChange, order }) => {
  const isCompleted = order.status === "COMPLETED";
  const isReceived = order.status === "RECEIVED";
  const nextStatus = order.status === "RECEIVED" ? "PREPARING" : order.status === "PREPARING" ? "COMPLETED" : null;
  return <article className={`overflow-hidden rounded-[10px] bg-white shadow-[0_3px_8px_rgba(27,27,30,0.2)] dark:bg-surface-container-low ${isCompleted ? "opacity-70" : ""}`}>
    <div className="flex items-center justify-between p-stack-md">
      <div><p className="text-headline-md">#{order.orderNumber}</p><p className="mt-2 text-label-sm text-on-surface-variant">{formatDate(order.createdAt)}</p></div>
      <div className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-label-lg ${isReceived ? "border-blue-500/20 bg-blue-50 text-blue-600" : isCompleted ? "border-success/20 bg-success/10 text-success" : "border-primary/20 bg-primary-fixed text-primary"}`}><CheckCircleIcon size={16} />{statusLabels[order.status]}</div>
    </div>
    <ul className="flex flex-col gap-3 border-t border-outline-variant/70 p-stack-md">{order.items.map((item, index) => <li key={`${item.menuName}-${index}`} className="flex items-start justify-between border-b border-outline-variant pb-3 last:border-0">
      <div className={isCompleted ? "line-through" : ""}><p className="text-body-lg font-bold">{item.quantity}x {item.menuName}</p>{item.options.length > 0 && <p className="text-body-md text-on-surface-variant">{item.options.map((option) => option.name).join(" · ")}</p>}</div>
      <span className={`shrink-0 text-body-lg font-semibold ${isCompleted ? "line-through" : ""}`}>{Number(item.subtotal).toLocaleString("ko-KR")}원</span>
    </li>)}</ul>
    <div className="flex items-center justify-between border-t border-outline-variant/70 p-stack-md">
      <div><p className="text-label-sm text-on-surface-variant">총 결제금액</p><p className={`text-headline-sm ${isCompleted ? "line-through" : ""}`}>{Number(order.totalPrice).toLocaleString("ko-KR")}원</p></div>
      {nextStatus && <button className={`rounded px-4 py-2 text-label-lg font-bold text-white disabled:opacity-50 ${isReceived ? "bg-blue-600 hover:bg-blue-700" : "bg-primary-container hover:bg-primary"}`} disabled={busy} type="button" onClick={() => onStatusChange(order, nextStatus)}>{busy ? "변경 중..." : nextStatus === "PREPARING" ? "조리 시작" : "조리 완료"}</button>}
    </div>
  </article>;
};

const OrderHistoryPage = () => {
  const storeId = getAdminSession().store.id;
  const [filter, setFilter] = useState(filters[0]);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState({ content: [], totalPages: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const displayedOrders = sortOrders(filterOrdersByStatus(result.content, filter.statuses));

  useEffect(() => {
    let ignore = false;
    getOrders(storeId, { page, statuses: filter.statuses })
      .then((response) => { if (!ignore) setResult(response); })
      .catch((requestError) => { if (!ignore) setError(requestError.message); })
      .finally(() => { if (!ignore) setIsLoading(false); });
    return () => { ignore = true; };
  }, [filter, page, storeId]);

  useEffect(() => {
    if (filter.value !== "active" || page !== 0) return undefined;
    return subscribeToOrders(storeId, (order) => {
      setResult((current) => current.content.some((item) => item.id === order.id)
        ? current
        : { ...current, content: [order, ...current.content].slice(0, 20), totalElements: (current.totalElements || 0) + 1 });
    });
  }, [filter, page, storeId]);

  const handleStatusChange = async (order, status) => {
    setBusyId(order.id);
    setError("");
    try {
      const updated = await updateOrderStatus(storeId, order.id, status);
      setResult((current) => ({
        ...current,
        content: updateVisibleOrders(current.content, updated, filter.value === "active"),
      }));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  };

  return <AdminLayout mainClassName="overflow-y-scroll [scrollbar-gutter:stable]" surfaceClassName="bg-white dark:bg-background">
    <h1 className="mb-8 text-headline-lg-mobile"><span className="text-primary">주문</span>을 확인하고 관리해요</h1>
    <div className="mb-stack-lg flex w-full gap-2 rounded-lg border border-outline-variant bg-surface-container-high p-1">{filters.map((item) => <button key={item.value} className={`flex-1 rounded-md px-6 py-2 text-label-lg ${filter.value === item.value ? "bg-primary-container font-bold text-white" : ""}`} type="button" onClick={() => { setIsLoading(true); setError(""); setFilter(item); setPage(0); }}>{item.label}</button>)}</div>
    {error && <p className="mb-4 text-error" role="alert">{error}</p>}
    {isLoading ? <p>주문을 불러오는 중...</p> : displayedOrders.length === 0 ? (
      <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-outline-variant bg-surface-container-low px-6 py-12 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary-fixed text-primary">
          <OrdersIcon size={30} />
        </div>
        <p className="text-headline-sm text-on-surface">
          {filter.value === "active" ? "진행 중인 주문이 없어요" : "완료된 주문이 없어요"}
        </p>
        <p className="mt-2 text-body-md text-on-surface-variant">
          {filter.value === "active" ? "새 주문이 들어오면 이곳에 표시됩니다." : "완료 처리된 주문이 이곳에 표시됩니다."}
        </p>
      </div>
    ) : <div className="grid grid-cols-1 gap-stack-md">{displayedOrders.map((order) => <OrderCard key={order.id} busy={busyId === order.id} order={order} onStatusChange={handleStatusChange} />)}</div>}
    {result.totalPages > 1 && <nav aria-label="주문 페이지" className="mt-stack-lg flex items-center justify-center gap-2"><button disabled={page === 0} type="button" onClick={() => { setIsLoading(true); setPage((current) => current - 1); }}>이전</button>{Array.from({ length: result.totalPages }, (_, index) => <button key={index} aria-current={page === index ? "page" : undefined} className={`h-9 w-9 rounded ${page === index ? "bg-primary-container text-white" : "border"}`} type="button" onClick={() => { setIsLoading(true); setPage(index); }}>{index + 1}</button>)}<button disabled={page + 1 >= result.totalPages} type="button" onClick={() => { setIsLoading(true); setPage((current) => current + 1); }}>다음</button></nav>}
  </AdminLayout>;
};

export default OrderHistoryPage;
