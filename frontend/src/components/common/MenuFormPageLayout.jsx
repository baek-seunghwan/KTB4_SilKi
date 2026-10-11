import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getAdminSession } from "../../api/client";
import { createMenu, getMenu, updateMenu, uploadMenuImage } from "../../api/menus";
import { ImageUploadIcon } from "../icons";
import AdminTopBar from "../layout/AdminTopBar";
import MobileLayout from "../layout/MobileLayout";
import MenuFormBottomAction from "./MenuFormBottomAction";

const categories = [
  { label: "커피", value: "COFFEE" },
  { label: "음료", value: "BEVERAGE" },
  { label: "차", value: "TEA" },
];
const sweetnesses = ["LOW", "MEDIUM", "HIGH"];
const sweetnessLabels = ["낮음", "보통", "높음"];

const MenuFormPageLayout = ({ menuId, saveLabel = "메뉴 저장", title }) => {
  const navigate = useNavigate();
  const storeId = getAdminSession()?.store?.id ?? null;
  const [form, setForm] = useState({
    category: "COFFEE", name: "", description: "", price: "", imageKey: null,
    availableTemperatures: ["HOT", "ICE"], defaultSweetness: "MEDIUM", caffeinated: true,
    extraShotAvailable: false,
  });
  const [imageFile, setImageFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [isLoading, setIsLoading] = useState(Boolean(menuId && storeId));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!menuId || !storeId) return;
    getMenu(storeId, menuId)
      .then((menu) => {
        setForm({ ...menu, price: String(menu.price) });
        setPreviewUrl(menu.imageUrl || "");
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setIsLoading(false));
  }, [menuId, storeId]);

  useEffect(() => {
    if (!previewUrl.startsWith("blob:")) return undefined;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const updateField = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const visibleError = error || (menuId && !storeId ? "로그인 후 메뉴 정보를 불러올 수 있어요." : "");
  const toggleTemperature = (temperature) => setForm((current) => ({
    ...current,
    availableTemperatures: current.availableTemperatures.includes(temperature)
      ? current.availableTemperatures.filter((value) => value !== temperature)
      : [...current.availableTemperatures, temperature],
  }));

  const handleSave = async () => {
    if (!storeId) {
      setError("임시 접근 중에는 메뉴를 저장할 수 없어요.");
      return;
    }
    if (!form.name.trim() || !form.price || form.availableTemperatures.length === 0) {
      setError("메뉴명, 가격, 온도를 확인해주세요.");
      return;
    }
    setError("");
    setIsSaving(true);
    try {
      const imageKey = imageFile ? (await uploadMenuImage(storeId, imageFile)).imageKey : form.imageKey;
      const body = {
        category: form.category,
        name: form.name.trim(),
        description: form.description.trim() || null,
        price: Number(form.price),
        imageKey,
        availableTemperatures: form.availableTemperatures,
        defaultSweetness: form.defaultSweetness,
        caffeinated: form.caffeinated,
        extraShotAvailable: form.extraShotAvailable,
      };
      if (menuId) await updateMenu(storeId, menuId, body);
      else await createMenu(storeId, body);
      navigate("/menu", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <MobileLayout contentClassName="flex h-[100dvh] w-full flex-col overflow-hidden" surfaceClassName="bg-white dark:bg-background">
      <AdminTopBar showBusinessStatus={false} title={title} onBack={() => navigate(-1)} />
      <main className="menu-form-scrollbar mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col gap-stack-md overflow-y-auto overscroll-contain bg-background px-container py-stack-lg pb-10">
        {isLoading ? (
          <div className="flex min-h-64 items-center justify-center text-body-md text-on-surface-variant">메뉴를 불러오는 중...</div>
        ) : (
          <>
            <section className="shrink-0 overflow-hidden rounded-2xl bg-surface-container-lowest p-stack-md shadow-[0_3px_8px_rgba(27,27,30,0.12)]">
              <h2 className="mb-stack-md text-headline-sm text-on-surface">메뉴 기본 정보</h2>
              <div className="flex flex-col gap-stack-md">
                <div className="flex flex-col gap-stack-sm">
                  <label className="text-label-lg text-on-surface" htmlFor="imageUpload">메뉴 이미지</label>
                  <label className={`group relative flex h-52 cursor-pointer items-center justify-center overflow-hidden rounded-xl border border-dashed transition-colors ${previewUrl ? "border-primary/40 bg-surface" : "border-outline bg-surface-container hover:border-primary hover:bg-primary-fixed/30"}`} htmlFor="imageUpload">
                    {previewUrl ? (
                      <>
                        <img alt="메뉴 이미지" className="absolute inset-0 h-full w-full object-cover" src={previewUrl} />
                        <span className="absolute inset-x-0 bottom-0 bg-black/55 py-2 text-center text-label-lg text-white">이미지 변경</span>
                      </>
                    ) : (
                      <span className="flex flex-col items-center gap-2 text-body-md text-on-surface-variant"><ImageUploadIcon className="text-primary" size={44} />이미지를 업로드해주세요<span className="text-label-sm text-on-surface-muted">JPG, PNG · 최대 5MB</span></span>
                    )}
                    <input accept="image/*" className="hidden" id="imageUpload" type="file" onChange={(event) => { const file = event.target.files?.[0] || null; setImageFile(file); if (file) setPreviewUrl(URL.createObjectURL(file)); }} />
                  </label>
                </div>

                <label className="flex flex-col gap-stack-sm text-label-lg text-on-surface">메뉴명
                  <input className="h-12 rounded-lg border border-transparent bg-surface-container px-container text-body-lg outline-none transition-all placeholder:text-on-surface-muted focus:border-primary focus:ring-2 focus:ring-primary/10" placeholder="메뉴명을 입력해주세요" required value={form.name} onChange={(event) => updateField("name", event.target.value)} />
                </label>

                <section className="flex flex-col gap-stack-sm">
                  <span className="text-label-lg text-on-surface">카테고리</span>
                  <div className="grid grid-cols-3 gap-gutter">{categories.map((item) => <label key={item.value} className="cursor-pointer"><input checked={form.category === item.value} className="peer sr-only" name="category" type="radio" onChange={() => updateField("category", item.value)} /><span className="flex h-11 items-center justify-center rounded-full border border-outline-variant bg-surface text-body-md text-on-surface-variant transition-all peer-checked:border-primary peer-checked:bg-primary-container peer-checked:font-semibold peer-checked:text-white">{item.label}</span></label>)}</div>
                </section>

                <label className="flex flex-col gap-stack-sm text-label-lg text-on-surface">가격
                  <div className="flex items-center rounded-lg border border-transparent bg-surface-container px-container transition-all focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/10"><input className="h-12 w-full bg-transparent text-right text-body-lg outline-none placeholder:text-on-surface-muted" inputMode="numeric" placeholder="0" value={form.price ? Number(form.price).toLocaleString("ko-KR") : ""} onChange={(event) => updateField("price", event.target.value.replace(/\D/g, ""))} /><span className="ml-2 text-body-lg text-on-surface-variant">원</span></div>
                </label>

                <label className="flex flex-col gap-stack-sm text-label-lg text-on-surface">메뉴 설명
                  <textarea className="h-28 resize-none rounded-lg border border-transparent bg-surface-container p-container text-body-lg outline-none transition-all placeholder:text-on-surface-muted focus:border-primary focus:ring-2 focus:ring-primary/10" placeholder="메뉴 설명을 작성해주세요" value={form.description || ""} onChange={(event) => updateField("description", event.target.value)} />
                </label>
              </div>
            </section>

            <section className="shrink-0 rounded-2xl bg-surface-container-lowest p-stack-md shadow-[0_3px_8px_rgba(27,27,30,0.12)]">
              <div className="mb-stack-md"><h2 className="text-headline-sm text-on-surface">판매 옵션</h2><p className="mt-1 text-body-md text-on-surface-variant">주문할 때 사용할 기본 옵션을 설정해주세요.</p></div>
              <div className="flex flex-col gap-stack-lg">
                <section className="flex flex-col gap-stack-sm">
                  <span className="text-label-lg text-on-surface">제공 온도</span>
                  <div className="grid grid-cols-2 gap-gutter">{[{ value: "HOT", label: "따뜻하게", caption: "HOT" }, { value: "ICE", label: "차갑게", caption: "ICE" }].map((item) => <label key={item.value} className="cursor-pointer"><input checked={form.availableTemperatures.includes(item.value)} className="peer sr-only" type="checkbox" onChange={() => toggleTemperature(item.value)} /><span className="flex h-14 items-center justify-between rounded-xl border border-outline-variant bg-surface px-container transition-all peer-checked:border-primary peer-checked:bg-primary-fixed peer-checked:text-primary"><span className="text-body-md font-semibold">{item.label}</span><span className="text-label-sm">{item.caption}</span></span></label>)}</div>
                </section>

                <section className="rounded-xl bg-surface-container p-container">
                  <div className="mb-stack-md flex items-center justify-between"><label className="text-label-lg text-on-surface" htmlFor="sweetness">기본 당도</label><span className="rounded-full bg-primary-fixed px-3 py-1 text-label-lg text-primary">{sweetnessLabels[sweetnesses.indexOf(form.defaultSweetness)]}</span></div>
                  <input className="h-2 w-full cursor-pointer accent-primary" id="sweetness" max="2" min="0" step="1" type="range" value={sweetnesses.indexOf(form.defaultSweetness)} onChange={(event) => updateField("defaultSweetness", sweetnesses[Number(event.target.value)])} />
                  <div className="mt-2 flex justify-between text-label-sm text-on-surface-variant">{sweetnessLabels.map((label) => <span key={label}>{label}</span>)}</div>
                </section>

                <label className="flex cursor-pointer items-center justify-between rounded-xl border border-outline-variant bg-surface px-container py-3">
                  <span><span className="block text-label-lg text-on-surface">카페인 포함</span><span className="mt-1 block text-body-md text-on-surface-variant">카페인이 들어간 메뉴인지 표시해요.</span></span>
                  <span className="relative ml-4 shrink-0"><input checked={form.caffeinated} className="peer sr-only" type="checkbox" onChange={(event) => updateField("caffeinated", event.target.checked)} /><span className="block h-8 w-14 rounded-full bg-surface-container-highest transition-colors peer-checked:bg-primary-container" /><span className="absolute left-1 top-1 h-6 w-6 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-6" /></span>
                </label>

                <label className="flex cursor-pointer items-center justify-between rounded-xl border border-outline-variant bg-surface px-container py-3">
                  <span><span className="block text-label-lg text-on-surface">샷 추가 가능</span><span className="mt-1 block text-body-md text-on-surface-variant">주문 시 최대 2샷까지 추가할 수 있어요.</span></span>
                  <span className="relative ml-4 shrink-0"><input checked={form.extraShotAvailable} className="peer sr-only" type="checkbox" onChange={(event) => updateField("extraShotAvailable", event.target.checked)} /><span className="block h-8 w-14 rounded-full bg-surface-container-highest transition-colors peer-checked:bg-primary-container" /><span className="absolute left-1 top-1 h-6 w-6 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-6" /></span>
                </label>
              </div>
            </section>

            {visibleError && <p className="shrink-0 rounded-xl bg-error-container px-container py-3 text-body-md text-error" role="alert">{visibleError}</p>}
          </>
        )}
      </main>
      <MenuFormBottomAction disabled={isLoading || isSaving} label={isSaving ? "저장 중..." : saveLabel} onClick={handleSave} />
    </MobileLayout>
  );
};

export default MenuFormPageLayout;
