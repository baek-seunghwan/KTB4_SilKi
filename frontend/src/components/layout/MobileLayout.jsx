const MobileLayout = ({
  children,
  contentClassName = "flex min-h-[inherit] w-full flex-col items-center justify-between px-container py-container",
  surfaceClassName = "bg-surface-bright",
}) => {
  return (
    <div
      className={`mobile-layout ${surfaceClassName} text-on-surface select-none`}
    >
      <div className={contentClassName}>{children}</div>
    </div>
  );
};

export default MobileLayout;
