import { useParams } from "react-router-dom";
import MenuFormPageLayout from "../components/common/MenuFormPageLayout";

const EditMenuPage = () => {
  const { menuId } = useParams();
  return <MenuFormPageLayout menuId={menuId} saveLabel="메뉴 수정" title="메뉴 수정" />;
};

export default EditMenuPage;
