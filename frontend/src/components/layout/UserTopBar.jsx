import { Link } from "react-router-dom";
import silkiKorWhiteLogo from "../../assets/silki_kor_white_logo.png";

const UserTopBar = ({
  actionLabel = "도움버튼",
  onActionClick,
}) => {
  return (
    <header className="relative z-50 flex h-24 w-full shrink-0 items-center justify-between border-b-2 border-primary-container bg-primary-container px-3 min-[400px]:px-6">
      <Link
        to="/"
        aria-label="처음으로"
        className="flex h-[88px] min-w-[80px] items-center justify-center whitespace-nowrap rounded-full px-2 text-[20px] font-extrabold text-white transition-colors duration-150 active:scale-95 min-[400px]:min-w-[108px] min-[400px]:px-4 min-[400px]:text-2xl"
      >
        처음으로
      </Link>

      <img
        src={silkiKorWhiteLogo}
        alt="실키 로고"
        className="h-10 w-auto object-contain"
      />

      <button
        type="button"
        aria-label={actionLabel}
        onClick={onActionClick}
        className="flex h-[88px] min-w-[80px] items-center justify-center whitespace-nowrap rounded-full px-2 text-[20px] font-extrabold text-white transition-colors duration-150 active:scale-95 min-[400px]:min-w-[108px] min-[400px]:px-4 min-[400px]:text-2xl"
      >
        {actionLabel}
      </button>
    </header>
  );
};

export default UserTopBar;
