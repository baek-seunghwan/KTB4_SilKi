import { useEffect, useState } from "react";
import silkiKorLogo from "../../assets/silki_kor_logo.png";
import silkiKorWhiteLogo from "../../assets/silki_kor_white_logo.png";
import { ArrowBackIcon } from "../icons";

const BUSINESS_STATUS_STORAGE_KEY = "silki-business-open";

const AdminTopBar = ({
  onBack,
  showBusinessStatus = true,
  title,
}) => {
  const [isOpen, setIsOpen] = useState(() => {
    return localStorage.getItem(BUSINESS_STATUS_STORAGE_KEY) !== "false";
  });

  useEffect(() => {
    const handleBusinessStatusChange = (event) => {
      setIsOpen(event.detail.isOpen);
    };

    window.addEventListener(
      "business-status-change",
      handleBusinessStatusChange,
    );

    return () => {
      window.removeEventListener(
        "business-status-change",
        handleBusinessStatusChange,
      );
    };
  }, []);

  return (
    <header className="relative flex h-16 shrink-0 items-center justify-between border-b border-outline-variant bg-surface px-container text-primary transition-colors duration-200">
      {onBack ? (
        <button
          aria-label="Go Back"
          className="flex h-12 w-12 items-center justify-center rounded-full text-on-surface-variant transition-colors duration-200 hover:bg-surface-container-high active:scale-95"
          type="button"
          onClick={onBack}
        >
          <ArrowBackIcon size={24} />
        </button>
      ) : (
        <div className="flex h-8 items-center gap-2">
          <img
            alt="실키 아이콘"
            className="h-8 w-8 object-contain"
            src="/skicon.svg"
          />
          <img
            alt="실키 로고"
            className="h-6 w-auto object-contain dark:hidden"
            src={silkiKorLogo}
          />
          <img
            alt="실키 로고"
            className="hidden h-6 w-auto object-contain dark:block"
            src={silkiKorWhiteLogo}
          />
        </div>
      )}

      {title && (
        <h1 className="absolute left-1/2 -translate-x-1/2 text-headline-md font-bold text-primary">
          {title}
        </h1>
      )}

      {showBusinessStatus ? (
        <div className="flex h-9 w-[112px] items-center justify-center gap-2 rounded-full border border-primary-container bg-primary-container px-3 text-body-md font-bold text-white">
          <span
            aria-hidden="true"
            className={`h-3 w-3 rounded-full ${
              isOpen ? "bg-success" : "bg-outline"
            }`}
          />
          <span>
            {isOpen ? "영업 중" : "영업 종료"}
          </span>
        </div>
      ) : (
        <div className="h-12 w-12" />
      )}
    </header>
  );
};

export default AdminTopBar;
