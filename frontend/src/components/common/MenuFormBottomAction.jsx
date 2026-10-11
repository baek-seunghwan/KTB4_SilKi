const MenuFormBottomAction = ({ disabled = false, label = "메뉴 저장", onClick }) => {
  return (
    <div className="shrink-0 rounded-t-[10px] bg-white p-container pb-[calc(16px+env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(27,27,30,0.12)] dark:bg-surface-container-low">
      <button
        className="flex h-12 w-full items-center justify-center rounded-lg bg-primary-container text-headline-sm text-on-primary transition-colors active:scale-[0.98] disabled:opacity-50"
        disabled={disabled}
        type="button"
        onClick={onClick}
      >
        {label}
      </button>
    </div>
  );
};

export default MenuFormBottomAction;
