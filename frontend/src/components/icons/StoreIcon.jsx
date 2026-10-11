/** 가게 아이콘 */
const StoreIcon = ({ size = 22, className = "" }) => {
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
      <path d="M3 10h18" />
      <path d="M5 10V7.2c0-.8.6-1.5 1.4-1.6l11.2-1.4c.8-.1 1.4.5 1.4 1.3V10" />
      <path d="M5 10v9h14v-9" />
      <path d="M9 19v-5h6v5" />
      <path d="M4 10c0 1.1.9 2 2 2s2-.9 2-2" />
      <path d="M8 10c0 1.1.9 2 2 2s2-.9 2-2" />
      <path d="M12 10c0 1.1.9 2 2 2s2-.9 2-2" />
      <path d="M16 10c0 1.1.9 2 2 2s2-.9 2-2" />
    </svg>
  );
};

export default StoreIcon;
