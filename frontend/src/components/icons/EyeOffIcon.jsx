/** 비밀번호 숨김 아이콘 */
const EyeOffIcon = ({ size = 16, className = "" }) => {
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
      <path d="m3 3 18 18" />
      <path d="M10.6 10.6A2 2 0 0 0 13.4 13.4" />
      <path d="M9.9 4.4A10.3 10.3 0 0 1 12 4c6.5 0 10 8 10 8a17.8 17.8 0 0 1-3.2 4.3" />
      <path d="M6.6 6.6A17.2 17.2 0 0 0 2 12s3.5 8 10 8a10.4 10.4 0 0 0 4.8-1.2" />
    </svg>
  );
};

export default EyeOffIcon;
