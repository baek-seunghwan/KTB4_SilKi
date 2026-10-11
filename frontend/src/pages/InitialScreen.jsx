import { Link } from "react-router-dom";
import { TouchIcon } from "../components/icons";
import MobileLayout from "../components/layout/MobileLayout";

const InitialScreen = () => {
  return (
    <MobileLayout surfaceClassName="customer-page bg-surface-bright">
      <div aria-hidden="true" className="w-full flex-1" />

      <main className="z-10 flex w-full flex-1 flex-col items-center justify-center px-8">
        <div className="group relative">
          <div className="logo-reveal relative flex size-32 items-center justify-center transition-transform duration-500 group-hover:scale-105">
            <img
              src="/skicon.svg"
              alt="실키 로고"
              className="logo-reveal-color size-full object-contain"
            />
            <img
              src="/skicon.svg"
              alt=""
              aria-hidden="true"
              className="logo-reveal-white absolute inset-0 size-full object-contain"
            />
          </div>
        </div>

        <p className="mt-10 text-center text-[26px] font-extrabold leading-9 text-on-surface-muted">
          말씀만 하세요,
          <br />
          주문은 <span className="text-primary">실키</span>가 도와드릴게요
        </p>
      </main>

      <footer className="z-10 mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-end gap-3 pb-20">
        <Link
          to="/qr-scan"
          className="flex w-full max-w-[280px] items-center justify-center gap-2 rounded-2xl bg-primary-container px-8 py-5 text-2xl font-bold text-on-primary transition-all duration-150 ease-out focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary-fixed-dim/50"
        >
          <TouchIcon size={30} />
          <span className="font-bold">주문하기</span>
        </Link>

        <Link
          to="/login"
          className="py-2 text-[12px] text-on-surface-muted underline underline-offset-4 transition-colors duration-200 hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-fixed-dim"
        >
          사장님이신가요?
        </Link>
      </footer>
    </MobileLayout>
  );
};

export default InitialScreen;
