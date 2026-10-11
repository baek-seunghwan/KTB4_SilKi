/** 메뉴 아이콘 */
const MenuIcon = ({ size = 22, className = "" }) => {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      focusable="false"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M4 3v18" />
      <path d="M8 3v18" />
      <path d="M4 8h4" />
      <path d="M15 3v8a3 3 0 0 0 6 0V3" />
      <path d="M18 14v7" />
    </svg>
  );
};

export default MenuIcon;
