package kr.ktb.silko_be.store;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import kr.ktb.silko_be.auth.AdminUser;
import org.junit.jupiter.api.Test;

class PublicStoreControllerTest {
    @Test
    void returnsOrderAvailableWhenStoreIsOpen() {
        var service = mock(StoreService.class);
        var store = store();
        when(service.requireStore(store.getId())).thenReturn(store);

        var response = new PublicStoreController(service).orderContext(store.getId());

        assertThat(response.storeId()).isEqualTo(store.getId());
        assertThat(response.storeName()).isEqualTo("강남점");
        assertThat(response.operatingStatus()).isEqualTo(OperatingStatus.OPEN);
        assertThat(response.orderAvailable()).isTrue();
        assertThat(response.message()).isEqualTo("현재 주문 가능합니다.");
    }

    @Test
    void returnsOrderUnavailableWhenStoreIsClosed() {
        var service = mock(StoreService.class);
        var store = store();
        store.changeStatus(OperatingStatus.CLOSED);
        when(service.requireStore(store.getId())).thenReturn(store);

        var response = new PublicStoreController(service).orderContext(store.getId());

        assertThat(response.operatingStatus()).isEqualTo(OperatingStatus.CLOSED);
        assertThat(response.orderAvailable()).isFalse();
        assertThat(response.message()).isEqualTo("현재 영업이 종료되었습니다.");
    }

    @Test
    void returnsPublicStoreStatus() {
        var service = mock(StoreService.class);
        var store = store();
        when(service.requireStore(store.getId())).thenReturn(store);

        var response = new PublicStoreController(service).status(store.getId());

        assertThat(response.status()).isEqualTo(OperatingStatus.OPEN);
    }

    private Store store() {
        return new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    }
}
