import AdminBottomNav from "./AdminBottomNav";
import AdminTopBar from "./AdminTopBar";
import MobileLayout from "./MobileLayout";

const AdminLayout = ({
  children,
  mainClassName = "",
  surfaceClassName = "bg-background",
}) => {
  return (
    <MobileLayout
      contentClassName="flex h-[100dvh] w-full flex-col overflow-hidden"
      surfaceClassName={surfaceClassName}
    >
      <AdminTopBar />
      <main
        className={`mx-auto w-full max-w-3xl flex-1 overflow-y-auto overscroll-contain px-container py-stack-lg ${mainClassName}`}
      >
        {children}
      </main>
      <AdminBottomNav />
    </MobileLayout>
  );
};

export default AdminLayout;
