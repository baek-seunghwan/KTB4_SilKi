package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.UUID;
import kr.ktb.silko_be.ai.MenuReindexPublisher;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreService;
import org.junit.jupiter.api.Test;

class MenuServicePublicDetailTest {
    private final MenuRepository repository = mock(MenuRepository.class);
    private final MenuService service = new MenuService(
        repository,
        mock(StoreService.class),
        mock(ImageStorage.class),
        mock(MenuReindexPublisher.class),
        mock(MenuOptionService.class)
    );

    @Test
    void resolvesOnlyAMenuOwnedByTheRequestedStore() {
        var store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
        var menu = new Menu(store, MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼", 4500, null);
        when(repository.findByIdAndStoreId(menu.getId(), store.getId())).thenReturn(Optional.of(menu));

        var resolved = service.getPublic(store.getId(), menu.getId());

        assertThat(resolved).isSameAs(menu);
        verify(repository).findByIdAndStoreId(menu.getId(), store.getId());
    }

    @Test
    void hidesAnotherStoresMenuBehindMenuNotFound() {
        var requestedStoreId = UUID.randomUUID();
        var otherStoreMenuId = UUID.randomUUID();
        when(repository.findByIdAndStoreId(otherStoreMenuId, requestedStoreId))
            .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getPublic(requestedStoreId, otherStoreMenuId))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status().value()).isEqualTo(404);
                assertThat(exception.code()).isEqualTo("MENU_NOT_FOUND");
            });
        verify(repository).findByIdAndStoreId(otherStoreMenuId, requestedStoreId);
    }
}
