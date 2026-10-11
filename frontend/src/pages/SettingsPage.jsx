import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { clearAdminSession, getAdminSession, setAdminSession } from "../api/client";
import { getStoreStatus, updateStoreStatus } from "../api/stores";
import {
  ImageUploadIcon,
  SettingsIcon,
  StoreIcon,
  TouchIcon,
} from "../components/icons";
import AdminLayout from "../components/layout/AdminLayout";

const BUSINESS_STATUS_STORAGE_KEY = "silki-business-open";

const ToggleSwitch = ({ checked, id, label, onChange, size = "md" }) => {
  const isLarge = size === "lg";

  return (
    <label
      className="relative inline-flex cursor-pointer items-center"
      htmlFor={id}
    >
      <span className="sr-only">{label}</span>
      <input
        checked={checked}
        className="peer sr-only"
        id={id}
        type="checkbox"
        onChange={(event) => onChange(event.target.checked)}
      />
      <span
        className={`rounded-full border border-outline-variant bg-surface-container-highest transition-colors duration-300 peer-checked:border-primary-container peer-checked:bg-primary-container ${
          isLarge ? "h-12 w-24" : "h-8 w-16"
        }`}
      />
      <span
        className={`absolute rounded-full bg-white shadow-sm transition-transform duration-300 ${
          isLarge
            ? "left-1 h-10 w-10 peer-checked:translate-x-12"
            : "left-1 h-6 w-6 peer-checked:translate-x-8"
        }`}
      />
    </label>
  );
};

const SettingCard = ({ children, className = "" }) => {
  return (
    <section
      className={`overflow-hidden rounded-[10px] bg-white p-stack-md shadow-[0_3px_8px_rgba(27,27,30,0.2)] dark:bg-surface-container-low ${className}`}
    >
      {children}
    </section>
  );
};

const SectionTitle = ({ children, icon: Icon }) => {
  return (
    <div className="mb-stack-md flex items-center gap-3 border-b border-outline-variant/70 pb-stack-sm">
      <Icon className="text-primary" size={22} />
      <h2 className="text-headline-sm text-on-surface">{children}</h2>
    </div>
  );
};

const SettingsPage = () => {
  const navigate = useNavigate();
  const session = getAdminSession();
  const storeId = session.store.id;
  const [isBusinessOpen, setIsBusinessOpen] = useState(() => {
    return localStorage.getItem(BUSINESS_STATUS_STORAGE_KEY) !== "false";
  });
  const [isStatusSaving, setIsStatusSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getStoreStatus(storeId)
      .then(({ status }) => {
        const isOpen = status === "OPEN";
        setIsBusinessOpen(isOpen);
        localStorage.setItem(BUSINESS_STATUS_STORAGE_KEY, String(isOpen));
      })
      .catch((requestError) => setError(requestError.message));
  }, [storeId]);

  const handleBusinessStatusChange = async (nextIsOpen) => {
    setIsStatusSaving(true);
    setError("");
    try {
      await updateStoreStatus(storeId, nextIsOpen ? "OPEN" : "CLOSED");
      setIsBusinessOpen(nextIsOpen);
      localStorage.setItem(BUSINESS_STATUS_STORAGE_KEY, String(nextIsOpen));
      setAdminSession({ ...session, store: { ...session.store, operatingStatus: nextIsOpen ? "OPEN" : "CLOSED" } });
      window.dispatchEvent(new CustomEvent("business-status-change", { detail: { isOpen: nextIsOpen } }));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsStatusSaving(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
      clearAdminSession();
      navigate("/login", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  return (
    <AdminLayout surfaceClassName="bg-white dark:bg-background">
      <div className="flex flex-col gap-stack-lg">
        <div>
          <h1 className="text-headline-lg-mobile text-on-surface">
            <span className="text-primary">매장 설정</span>을 관리해요
          </h1>
          <p className="mt-2 text-body-md text-on-surface-variant">
            영업 상태와 매장 정보를 한 곳에서 확인해요.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-stack-md">
          <SettingCard className="relative flex flex-col gap-stack-md p-stack-lg">
            <div className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/3 -translate-y-1/3 rounded-full bg-primary-container/10 blur-3xl" />
            <div>
              <div className="mb-2 flex items-center gap-2">
                <StoreIcon className="text-primary" size={22} />
                <h2 className="text-headline-sm text-on-surface">영업 상태</h2>
              </div>
              <p className="text-body-md text-on-surface-variant">
                {isBusinessOpen
                  ? "현재 새 주문을 받을 수 있어요."
                  : "현재 주문 접수가 중지된 상태예요."}
              </p>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-outline-variant bg-surface-container-low p-stack-md">
              <span
                className={`text-headline-md font-bold tracking-wider ${
                  isBusinessOpen ? "text-success" : "text-on-surface-variant"
                }`}
              >
                {isBusinessOpen ? "영업 중" : "영업 종료"}
              </span>
              <ToggleSwitch
                checked={isBusinessOpen}
                id="business-toggle"
                label="영업 상태 변경"
                size="lg"
                onChange={isStatusSaving ? () => {} : handleBusinessStatusChange}
              />
            </div>
          </SettingCard>

          <SettingCard>
            <SectionTitle icon={SettingsIcon}>화면 설정</SectionTitle>
            <div className="flex items-center justify-between gap-stack-md rounded-lg border border-outline-variant bg-surface-container-low p-stack-md">
              <div className="flex flex-col">
                <span className="text-headline-md font-bold tracking-wider text-on-surface-variant">
                  시스템 테마
                </span>
                <span className="text-body-md text-on-surface-variant">
                  휴대폰의 라이트·다크 모드 설정을 자동으로 따라가요.
                </span>
              </div>
            </div>
          </SettingCard>

          <SettingCard>
            <SectionTitle icon={TouchIcon}>매장 프로필</SectionTitle>
            <div className="flex flex-col gap-stack-md">
              <div className="flex items-center gap-4">
                <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-outline-variant bg-surface-container-highest text-on-surface-variant">
                  <ImageUploadIcon size={30} />
                </div>
                <div>
                  <h3 className="text-headline-sm text-on-surface">
                    {session.store.name}
                  </h3>
                  <p className="text-body-md text-on-surface-variant">
                    매장 ID: {session.store.id}
                  </p>
                </div>
              </div>

              <div className="mt-2 flex flex-col gap-stack-md">
                <div>
                  <label
                    className="mb-1 block text-label-sm uppercase tracking-wider text-on-surface-variant"
                    htmlFor="storePhone"
                  >
                    매장 연락처
                  </label>
                  <input
                    className="h-12 w-full rounded-lg border border-outline-variant bg-surface px-3 text-body-md text-on-surface outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    id="storePhone"
                    type="text"
                    defaultValue="02-1234-5678"
                  />
                </div>
                <div>
                  <label
                    className="mb-1 block text-label-sm uppercase tracking-wider text-on-surface-variant"
                    htmlFor="storeEmail"
                  >
                    문의 이메일
                  </label>
                  <input
                    className="h-12 w-full rounded-lg border border-outline-variant bg-surface px-3 text-body-md text-on-surface outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    id="storeEmail"
                    type="email"
                    defaultValue="silki-cafe@example.com"
                  />
                </div>
              </div>
            </div>
          </SettingCard>

          {error && <p className="text-body-md text-error" role="alert">{error}</p>}
          <button
            className="mx-auto mt-stack-md h-12 w-40 rounded-[10px] border border-primary bg-white text-headline-sm font-bold text-primary shadow-[0_3px_8px_rgba(27,27,30,0.12)] transition-colors hover:bg-primary-fixed active:scale-[0.98] dark:bg-surface-container-low"
            type="button"
            onClick={handleLogout}
          >
            로그아웃
          </button>
        </div>
      </div>
    </AdminLayout>
  );
};

export default SettingsPage;
