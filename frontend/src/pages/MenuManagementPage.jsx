import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getAdminSession } from "../api/client";
import { deleteMenu, getMenus, updateMenuSalesStatus } from "../api/menus";
import AdminLayout from "../components/layout/AdminLayout";
import { AddCartIcon, ChevronDownIcon, ChevronUpIcon, InfoIcon } from "../components/icons";

const categories = [
  { label: "커피", value: "COFFEE" },
  { label: "음료", value: "BEVERAGE" },
  { label: "차", value: "TEA" },
];

const formatWonPrice = (price) => `${Number(price).toLocaleString("ko-KR")}원`;

const ToggleSwitch = ({ checked, disabled, onChange }) => (
  <label className={`flex items-center ${disabled ? "cursor-wait opacity-60" : "cursor-pointer"}`}>
    <span className="relative">
      <input checked={checked} className="peer sr-only" disabled={disabled} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
      <span className={`block h-7 w-12 rounded-full transition-colors duration-300 ${checked ? "bg-primary-container" : "border border-outline-variant bg-surface-variant"}`} />
      <span className={`absolute left-1 top-1 h-5 w-5 rounded-full transition-transform duration-300 ${checked ? "translate-x-5 bg-white" : "bg-outline"}`} />
    </span>
  </label>
);

const MenuItem = ({ busy, item, onDeleteClick, onEditClick, onToggle }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isActive = item.salesStatus === "AVAILABLE";
  return (
    <article className="overflow-hidden rounded-[10px] bg-white shadow-[0_3px_8px_rgba(27,27,30,0.2)] transition-shadow dark:bg-surface-container-low">
      <div className="flex items-center justify-between p-stack-md">
        <div className="flex min-w-0 flex-1 items-center gap-stack-md">
          <div className={`relative h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest ${isActive ? "" : "grayscale"}`}>
            {item.imageUrl && <img alt={item.name} className="h-full w-full object-cover" src={item.imageUrl} />}
            {!isActive && <div className="absolute inset-0 bg-surface-container-highest/40" />}
          </div>
          <div className={`flex min-w-0 flex-col transition-opacity ${isActive ? "" : "opacity-50"}`}>
            <span className="truncate text-headline-sm text-on-surface">{item.name}</span>
            <span className="mt-1 text-body-lg font-bold text-on-surface">{formatWonPrice(item.price)}</span>
          </div>
        </div>
        <button aria-expanded={isExpanded} aria-label={isExpanded ? "메뉴 카드 접기" : "메뉴 카드 펼치기"} className="flex h-12 w-12 items-center justify-center rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary" type="button" onClick={() => setIsExpanded((current) => !current)}>{isExpanded ? <ChevronUpIcon size={24} /> : <ChevronDownIcon size={24} />}</button>
      </div>
      {isExpanded && <div className="border-t border-outline-variant/70 bg-white px-stack-md py-stack-sm dark:bg-surface-container-low">
        <div className="mb-stack-sm flex items-center justify-between rounded-xl bg-surface-container-low px-stack-md py-stack-sm">
          <span className="text-label-lg text-on-surface-variant">품절 상태</span>
          <ToggleSwitch checked={!isActive} disabled={busy} onChange={onToggle} />
        </div>
        <div className="grid grid-cols-2 gap-stack-sm">
          <button className="h-10 rounded-lg border border-outline-variant bg-surface text-label-lg text-on-surface transition-colors hover:bg-surface-container-low" type="button" onClick={onEditClick}>메뉴 수정</button>
          <button className="h-10 rounded-lg border border-error/40 bg-surface text-label-lg text-error transition-colors hover:bg-error-container disabled:opacity-50" disabled={busy} type="button" onClick={onDeleteClick}>메뉴 삭제</button>
        </div>
      </div>}
    </article>
  );
};

const SoldOutModal = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  return <div className="fixed inset-0 z-[100] flex items-center justify-center">
    <button aria-label="품절 처리 모달 닫기" className="absolute inset-0 bg-black/50 backdrop-blur-sm" type="button" onClick={onClose} />
    <div className="relative flex w-[320px] max-w-[90%] flex-col items-center rounded-2xl bg-surface p-6 text-center shadow-xl">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-surface-variant"><InfoIcon className="text-on-surface-variant" size={24} /></div>
      <h3 className="mb-2 text-headline-sm text-on-surface">품절 처리 완료</h3>
      <p className="mb-6 text-body-md text-on-surface-variant">해당 메뉴가 품절 처리되었습니다.</p>
      <button className="w-full rounded-xl bg-primary-container py-3 text-label-lg text-white transition-opacity hover:opacity-90" type="button" onClick={onClose}>확인</button>
    </div>
  </div>;
};

const DeleteConfirmModal = ({ busy, item, onCancel, onDelete }) => {
  if (!item) return null;
  return <div className="fixed inset-0 z-[100] flex items-center justify-center">
    <button aria-label="메뉴 삭제 모달 닫기" className="absolute inset-0 bg-black/50 backdrop-blur-sm" type="button" onClick={onCancel} />
    <div className="relative flex min-h-[180px] w-[320px] max-w-[90%] flex-col justify-center rounded-2xl bg-surface p-8 text-center shadow-xl">
      <h3 className="mb-8 text-headline-sm text-on-surface">메뉴를 삭제하시겠습니까?</h3>
      <div className="grid grid-cols-2 gap-stack-sm">
        <button className="h-12 rounded-xl border border-primary-container bg-white text-label-lg font-bold text-primary transition-colors hover:bg-primary-fixed" type="button" onClick={onCancel}>취소하기</button>
        <button className="h-12 rounded-xl bg-primary-container text-label-lg font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-50" disabled={busy} type="button" onClick={onDelete}>삭제하기</button>
      </div>
    </div>
  </div>;
};

const MenuManagementPage = () => {
  const navigate = useNavigate();
  const storeId = getAdminSession().store.id;
  const [category, setCategory] = useState(categories[0]);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState({ content: [], totalPages: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [showSoldOut, setShowSoldOut] = useState(false);

  useEffect(() => {
    let ignore = false;
    getMenus(storeId, category.value, page)
      .then((response) => { if (!ignore) setResult(response); })
      .catch((requestError) => { if (!ignore) setError(requestError.message); })
      .finally(() => { if (!ignore) setIsLoading(false); });
    return () => { ignore = true; };
  }, [category, page, storeId]);

  const handleToggle = async (item, soldOut) => {
    setBusyId(item.id);
    setError("");
    try {
      const updated = await updateMenuSalesStatus(storeId, item.id, soldOut ? "SOLD_OUT" : "AVAILABLE");
      setResult((current) => ({ ...current, content: current.content.map((menu) => menu.id === item.id ? updated : menu) }));
      if (soldOut) setShowSoldOut(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setBusyId(deleteTarget.id);
    try {
      await deleteMenu(storeId, deleteTarget.id);
      setDeleteTarget(null);
      if (result.content.length === 1 && page > 0) setPage((current) => current - 1);
      else setResult((current) => ({ ...current, content: current.content.filter((item) => item.id !== deleteTarget.id) }));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AdminLayout surfaceClassName="bg-white dark:bg-background">
      <div className="mb-stack-lg flex items-center justify-between">
        <h1 className="text-headline-lg-mobile text-on-surface"><span className="text-primary">메뉴</span>를 관리하실 수 있어요</h1>
      </div>

      <div className="no-scrollbar mb-stack-sm flex gap-stack-sm overflow-x-auto pb-2">
        {categories.map((item) => {
          const isSelected = category.value === item.value;
          return <button key={item.value} className={`h-9 whitespace-nowrap rounded-full border px-5 py-1 text-label-lg transition-colors ${isSelected ? "border-primary-container bg-primary-container text-white" : "border-outline-variant bg-surface text-on-surface-variant hover:border-outline"}`} type="button" onClick={() => { setIsLoading(true); setError(""); setCategory(item); setPage(0); }}>{item.label}</button>;
        })}
      </div>

      {error && <p className="mb-stack-md rounded-lg bg-error-container px-container py-3 text-body-md text-error" role="alert">{error}</p>}

      <section className="mb-stack-lg">
        <h2 className="mb-stack-md text-headline-md text-on-surface">{category.label}</h2>
        {isLoading ? <p className="text-body-md text-on-surface-variant">메뉴를 불러오는 중...</p> : result.content.length === 0 ? <p className="text-body-md text-on-surface-variant">등록된 메뉴가 없습니다.</p> : (
          <div className="flex flex-col gap-stack-md">
            {result.content.map((item) => <MenuItem key={item.id} busy={busyId === item.id} item={item} onDeleteClick={() => setDeleteTarget(item)} onEditClick={() => navigate(`/menu/edit/${item.id}`)} onToggle={(soldOut) => handleToggle(item, soldOut)} />)}
          </div>
        )}
      </section>

      {result.totalPages > 1 && <nav aria-label="메뉴 페이지" className="mb-stack-lg flex items-center justify-center gap-2">
        <button className="h-9 rounded-lg border border-outline-variant px-3 text-label-lg disabled:opacity-40" disabled={page === 0} type="button" onClick={() => { setIsLoading(true); setPage((current) => current - 1); }}>이전</button>
        {Array.from({ length: result.totalPages }, (_, index) => <button key={index} aria-current={page === index ? "page" : undefined} className={`h-9 w-9 rounded-lg text-label-lg ${page === index ? "bg-primary-container text-white" : "border border-outline-variant bg-surface text-on-surface"}`} type="button" onClick={() => { setIsLoading(true); setPage(index); }}>{index + 1}</button>)}
        <button className="h-9 rounded-lg border border-outline-variant px-3 text-label-lg disabled:opacity-40" disabled={page + 1 >= result.totalPages} type="button" onClick={() => { setIsLoading(true); setPage((current) => current + 1); }}>다음</button>
      </nav>}

      <div className="mt-stack-lg pb-stack-md">
        <button className="flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-primary-container text-headline-sm text-white shadow-lg transition-transform active:scale-[0.98]" type="button" onClick={() => navigate("/menu/add")}><AddCartIcon size={22} /><span>메뉴 추가</span></button>
      </div>

      <SoldOutModal isOpen={showSoldOut} onClose={() => setShowSoldOut(false)} />
      <DeleteConfirmModal busy={busyId === deleteTarget?.id} item={deleteTarget} onCancel={() => setDeleteTarget(null)} onDelete={handleDelete} />
    </AdminLayout>
  );
};

export default MenuManagementPage;
