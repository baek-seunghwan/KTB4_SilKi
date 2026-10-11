import { useLocation, useNavigate } from "react-router-dom";
import { MenuIcon, OrdersIcon, SettingsIcon } from "../icons";

const navItems = [
  { label: "주문내역", icon: OrdersIcon, path: "/orders" },
  { label: "메뉴관리", icon: MenuIcon, path: "/menu" },
  { label: "설정", icon: SettingsIcon, path: "/settings" },
];

const AdminBottomNav = () => {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav className="flex h-20 shrink-0 items-center justify-around rounded-t-[30px] border-t border-outline-variant bg-surface-container px-base pb-[env(safe-area-inset-bottom)] text-label-sm text-on-surface-variant shadow-[0_-8px_24px_rgba(27,27,30,0.12)]">
      {navItems.map(({ label, icon: Icon, path }) => {
        const isActive = path && location.pathname.startsWith(path);

        return (
          <button
            key={label}
            aria-current={isActive ? "page" : undefined}
            className="flex h-full flex-1 flex-col items-center justify-center gap-1 transition-transform duration-150 hover:text-on-surface active:scale-90"
            type="button"
            onClick={() => {
              if (path && location.pathname !== path) {
                navigate(path);
              }
            }}
          >
            <Icon className={isActive ? "text-primary-container" : ""} size={22} />
            <span className="mt-1">{label}</span>
          </button>
        );
      })}
    </nav>
  );
};

export default AdminBottomNav;
