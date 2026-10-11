import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { setAdminSession } from "../api/client";
import { getStores } from "../api/stores";
import {
  BadgeIcon,
  EyeIcon,
  EyeOffIcon,
  LockIcon,
} from "../components/icons";
import MobileLayout from "../components/layout/MobileLayout";

const LoginPage = () => {
  const navigate = useNavigate();
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const admin = await login(email, password, rememberMe);
      const [store] = await getStores();
      if (!store) throw new Error("등록된 매장이 없습니다.");
      setAdminSession({ adminName: admin.adminName, store });
      localStorage.setItem("silki-business-open", String(store.operatingStatus === "OPEN"));
      navigate("/menu", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <MobileLayout surfaceClassName="overflow-hidden bg-surface">
      <div className="flex min-h-[inherit] w-full items-center justify-center">
        <main className="relative w-full max-w-md p-stack-lg">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary-container opacity-10 blur-3xl"
          />

          <div className="relative z-10 mb-stack-lg text-center">
            <div className="mb-stack-sm flex justify-center">
              <img
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuCq-qSfol-D4YihNmFpRN22GqlokkKjbRT56mu1E9PB03VHtZhLfx6JGQHOzgXnG2ge2ghay6tWE_IwwW7giszE7kEH90DhcU0ST4XBf0w7O4noyQFRa65FzEXsaPBBRCUJymGGu1CWgiLtUgxgVDVZLnmfqUE6nWiVLwxvJoWD0ynPrwhtjoHZZGHgQjDAQY8h-MInbHGHfU_KYF75FZDdJ8lwKmeuvSFCDnuIwGtoj0a84PZATmJEObZRLDnIK6OOIg"
                alt="KioskAdmin Logo"
                className="h-28 w-28 object-contain"
              />
            </div>
            <h1 className="text-[28px] font-bold leading-[36px] text-primary">
              우리 매장 관리
            </h1>
            <p className="mt-stack-sm text-[13px] leading-[19px] text-on-surface-variant">
              <span className="font-bold text-primary">실키</span>에서 매장
              정보와 메뉴, 주문 내역을 한 번에 관리해요
            </p>
          </div>

          <form className="relative z-10 space-y-stack-md" onSubmit={handleSubmit}>
            <div>
              <label
                className="mb-stack-sm block text-[13px] font-semibold leading-[18px] text-on-surface-variant"
                htmlFor="store-id"
              >
                이메일
              </label>
              <div className="relative">
                <BadgeIcon
                  size={20}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
                />
                <input
                  className="h-12 w-full rounded-lg border border-outline-variant bg-surface-container-lowest py-3 pl-10 pr-3 text-body-md text-on-surface transition-colors placeholder:text-outline focus:border-primary-container focus:outline-none focus:ring-1 focus:ring-primary-container"
                  id="store-id"
                  placeholder="이메일을 입력해주세요"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>
            </div>

            <div>
              <div className="mb-stack-sm flex items-center justify-between">
                <label
                  className="block text-[13px] font-semibold leading-[18px] text-on-surface-variant"
                  htmlFor="password"
                >
                  비밀번호
                </label>
              </div>
              <div className="relative">
                <LockIcon
                  size={20}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
                />
                <input
                  className="h-12 w-full rounded-lg border border-outline-variant bg-surface-container-lowest py-3 pl-10 pr-10 text-body-md text-on-surface transition-colors placeholder:text-outline focus:border-primary-container focus:outline-none focus:ring-1 focus:ring-primary-container"
                  id="password"
                  placeholder="비밀번호를 입력해주세요"
                  type={isPasswordVisible ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  aria-label="Toggle password visibility"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant transition-colors hover:text-on-surface"
                  type="button"
                  onClick={() => setIsPasswordVisible((current) => !current)}
                >
                  {isPasswordVisible ? (
                    <EyeIcon size={16} />
                  ) : (
                    <EyeOffIcon size={16} />
                  )}
                </button>
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-2 text-body-md text-on-surface-variant">
              <input
                checked={rememberMe}
                className="h-4 w-4 accent-primary"
                type="checkbox"
                onChange={(event) => setRememberMe(event.target.checked)}
              />
              로그인 상태 유지
            </label>

            {error && <p className="text-body-md text-error" role="alert">{error}</p>}

            <div className="pt-stack-sm">
              <button
                className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-primary-container py-3 text-headline-sm font-semibold text-white transition-opacity hover:opacity-90 active:scale-95 disabled:opacity-50"
                disabled={isSubmitting}
                type="submit"
              >
                <span>{isSubmitting ? "로그인 중..." : "로그인"}</span>
              </button>
            </div>
          </form>

          <div className="relative z-10 mt-8 text-center">
            <a
              className="text-body-md text-on-surface-variant underline underline-offset-4 transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-fixed-dim"
              href="#"
            >
              사장님, <span className="font-bold text-primary">회원가입</span>이
              필요하세요?
            </a>
          </div>
        </main>
      </div>
    </MobileLayout>
  );
};

export default LoginPage;
