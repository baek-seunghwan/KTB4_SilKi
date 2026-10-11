const MagnifierOffButton = ({ className = "", onClick }) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-[320px] max-w-[calc(100%-48px)] items-center justify-center rounded-2xl bg-error px-6 py-6 text-[24px] font-extrabold text-white shadow-[0_14px_30px_rgba(239,68,68,0.28)] transition-transform duration-150 active:scale-95 ${className}`}
    >
      돋보기 끄기
    </button>
  );
};

export default MagnifierOffButton;
