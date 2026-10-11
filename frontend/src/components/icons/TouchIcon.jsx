/** 터치 아이콘 */
const TouchIcon = ({ size = 30, className = "" }) => {
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
      <path d="M9 11.5V6.75a2.25 2.25 0 0 1 4.5 0v5.75" />
      <path d="M13.5 10.5v-1a2 2 0 0 1 4 0v4" />
      <path d="M17.5 12v-.75a2 2 0 0 1 4 0V15a7 7 0 0 1-7 7h-1.25a6 6 0 0 1-4.8-2.4L5 15a2 2 0 0 1 3.1-2.5L9 13.6" />
    </svg>
  );
};

export default TouchIcon;
