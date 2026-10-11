import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { getAdminSession } from "./api/client";
import InitialScreen from "./pages/InitialScreen";
import AddMenuPage from "./pages/AddMenuPage";
import CartPage from "./pages/CartPage";
import EditMenuPage from "./pages/EditMenuPage";
import LoginPage from "./pages/LoginPage";
import MenuManagementPage from "./pages/MenuManagementPage";
import OrderHistoryPage from "./pages/OrderHistoryPage";
import OrderStatusPage from "./pages/OrderStatusPage";
import QRScanPage from "./pages/QRScanPage";
import SettingsPage from "./pages/SettingsPage";
import VoiceOrderPage from "./pages/VoiceOrderPage";

const AdminRoute = () =>
  getAdminSession()?.store?.id ? <Outlet /> : <Navigate to="/login" replace />;

const App = () => {
  return (
    <Routes>
      <Route path="/" element={<InitialScreen />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/qr-scan" element={<QRScanPage />} />
      <Route path="/voice-order" element={<VoiceOrderPage />} />
      <Route path="/cart" element={<CartPage />} />
      <Route path="/order-status/:orderId" element={<OrderStatusPage />} />
      <Route element={<AdminRoute />}>
        <Route path="/orders" element={<OrderHistoryPage />} />
        <Route path="/menu" element={<MenuManagementPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/menu/add" element={<AddMenuPage />} />
        <Route path="/menu/edit/:menuId" element={<EditMenuPage />} />
      </Route>
    </Routes>
  );
};

export default App;
