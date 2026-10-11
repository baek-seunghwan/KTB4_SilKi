/** 위 화살표 아이콘 */
const ChevronUpIcon = ({ size = 22, className = "" }) => {
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
      strokeWidth="2.5"
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="m18 15-6-6-6 6" />
    </svg>
  );
};

export default ChevronUpIcon;
