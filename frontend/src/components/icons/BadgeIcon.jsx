/** 이메일 입력 아이콘 */
const BadgeIcon = ({ size = 20, className = "" }) => {
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
      <rect width="16" height="14" x="4" y="6" rx="2" />
      <path d="M9 10h6" />
      <path d="M9 14h3" />
      <path d="M9 2h6v4H9z" />
    </svg>
  );
};

export default BadgeIcon;
