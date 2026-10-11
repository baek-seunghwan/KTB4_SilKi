package kr.ktb.silko_be.menu;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.StoreService;
import org.junit.jupiter.api.Test;

class MenuServiceTest {
    private final MenuRepository repository = mock(MenuRepository.class);
    private final StoreService storeService = mock(StoreService.class);
    private final MenuService service = new MenuService(repository, storeService, mock(ImageStorage.class),
        mock(kr.ktb.silko_be.ai.MenuReindexPublisher.class), mock(MenuOptionService.class));

    @Test
    void checksManagedStoreAndReturnsNotFoundForMissingDetail() {
        var storeId = UUID.randomUUID();
        var menuId = UUID.randomUUID();
        when(repository.findByIdAndStoreId(menuId, storeId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.detail(storeId, menuId))
            .isInstanceOfSatisfying(ApiException.class,
                exception -> org.assertj.core.api.Assertions.assertThat(exception.code()).isEqualTo("MENU_NOT_FOUND"));
        verify(storeService).requireManagedStore(storeId);
    }
}
