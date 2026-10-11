package kr.ktb.silko_be.menu;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.ai.MenuReindexPublisher;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MenuServiceReindexTest {
    private final MenuRepository repository = mock(MenuRepository.class);
    private final StoreService storeService = mock(StoreService.class);
    private final ImageStorage imageStorage = mock(ImageStorage.class);
    private final MenuReindexPublisher reindexPublisher = mock(MenuReindexPublisher.class);
    private final MenuOptionService optionService = mock(MenuOptionService.class);
    private final MenuService service = new MenuService(repository, storeService, imageStorage, reindexPublisher,
        optionService);
    private final Store store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    private Menu menu;

    @BeforeEach
    void setUp() {
        menu = new Menu(store, MenuCategory.COFFEE, "아메리카노", "고소한 원두", 4500, null,
            Set.of(Temperature.HOT, Temperature.ICE), DefaultSweetness.LOW, true, true);
        when(storeService.requireManagedStore(store.getId())).thenReturn(store);
        when(repository.findByIdAndStoreId(menu.getId(), store.getId())).thenReturn(Optional.of(menu));
    }

    @Test
    void publishesReindexAfterMenuCreation() {
        when(repository.save(any(Menu.class))).thenAnswer(invocation -> invocation.getArgument(0));

        var created = service.create(store.getId(), MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼",
            5000, null, Set.of(Temperature.HOT), DefaultSweetness.MEDIUM, true, true);

        verify(optionService).createDefaults(created);
        verify(reindexPublisher).publish(store.getId(), created.getId(), "menu.created");
    }

    @Test
    void publishesReindexAfterMenuUpdate() {
        service.update(store.getId(), menu.getId(), MenuCategory.COFFEE, "아이스 아메리카노",
            "시원한 커피", 4700, null, Set.of(Temperature.ICE), DefaultSweetness.LOW, true, true);

        verify(reindexPublisher).publish(store.getId(), menu.getId(), "menu.updated");
    }

    @Test
    void publishesReindexAfterMenuDeletion() {
        service.delete(store.getId(), menu.getId());

        verify(repository).delete(menu);
        verify(reindexPublisher).publish(store.getId(), menu.getId(), "menu.deleted");
    }

    @Test
    void publishesReindexAfterSalesStatusChange() {
        service.changeSalesStatus(store.getId(), menu.getId(), SalesStatus.SOLD_OUT);

        verify(reindexPublisher).publish(store.getId(), menu.getId(), "menu.sales_status_changed");
    }
}
