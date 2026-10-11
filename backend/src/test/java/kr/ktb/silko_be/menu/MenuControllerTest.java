package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreService;
import org.junit.jupiter.api.Test;

class MenuControllerTest {
    @Test
    void returnsMenuDetailWithImageKey() {
        var service = mock(MenuService.class);
        var imageStorage = mock(ImageStorage.class);
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var menu = new Menu(store, MenuCategory.COFFEE, "아메리카노", null, 4500, "stores/key");
        when(service.detail(store.getId(), menu.getId())).thenReturn(menu);

        var response = new MenuController(service, mock(StoreService.class), imageStorage)
            .detail(store.getId(), menu.getId());

        assertThat(response.imageKey()).isEqualTo("stores/key");
        verify(service).detail(store.getId(), menu.getId());
    }
}
