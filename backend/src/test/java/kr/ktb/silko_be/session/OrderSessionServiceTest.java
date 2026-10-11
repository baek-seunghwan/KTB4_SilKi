package kr.ktb.silko_be.session;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.Optional;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.store.OperatingStatus;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreRepository;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class OrderSessionServiceTest {
    @Test
    void createsActiveSessionForOpenStore() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var storeRepository = mock(StoreRepository.class);
        var service = new OrderSessionService(sessionRepository, storeRepository, 30);
        var store = store();
        when(storeRepository.findById(store.getId())).thenReturn(Optional.of(store));
        when(sessionRepository.saveAndFlush(any())).thenAnswer(invocation -> invocation.getArgument(0));
        var before = OffsetDateTime.now().plusMinutes(29);

        var session = service.create(store.getId());

        assertThat(session.getStoreId()).isEqualTo(store.getId());
        assertThat(session.getStatus()).isEqualTo(OrderSessionStatus.ACTIVE);
        assertThat(session.getCartVersion()).isZero();
        assertThat(session.getExpiresAt()).isAfter(before);
    }

    @Test
    void rejectsSessionForClosedStore() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var storeRepository = mock(StoreRepository.class);
        var service = new OrderSessionService(sessionRepository, storeRepository, 30);
        var store = store();
        store.changeStatus(OperatingStatus.CLOSED);
        when(storeRepository.findById(store.getId())).thenReturn(Optional.of(store));

        assertThatThrownBy(() -> service.create(store.getId()))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.CONFLICT);
                assertThat(exception.code()).isEqualTo("STORE_CLOSED");
            });
    }

    @Test
    void selectsTakeoutAndIncrementsCartVersion() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var service = new OrderSessionService(sessionRepository, mock(StoreRepository.class), 30);
        var session = new OrderSession(store(), OffsetDateTime.now().plusMinutes(30));
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));

        var result = service.selectFulfillment(session.getId(), 0, FulfillmentType.TAKEOUT);

        assertThat(result.getFulfillmentType()).isEqualTo(FulfillmentType.TAKEOUT);
        assertThat(result.getCartVersion()).isEqualTo(1);
        verify(sessionRepository).flush();
    }

    @Test
    void keepsVersionWhenSameFulfillmentIsSelectedAgain() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var service = new OrderSessionService(sessionRepository, mock(StoreRepository.class), 30);
        var session = new OrderSession(store(), OffsetDateTime.now().plusMinutes(30));
        session.selectFulfillment(FulfillmentType.DINE_IN);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));

        var result = service.selectFulfillment(session.getId(), 1, FulfillmentType.DINE_IN);

        assertThat(result.getCartVersion()).isEqualTo(1);
    }

    @Test
    void rejectsStaleVersionBeforeChangingFulfillment() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var service = new OrderSessionService(sessionRepository, mock(StoreRepository.class), 30);
        var session = new OrderSession(store(), OffsetDateTime.now().plusMinutes(30));
        session.incrementCartVersion();
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> service.selectFulfillment(session.getId(), 0, FulfillmentType.TAKEOUT))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.CONFLICT);
                assertThat(exception.code()).isEqualTo("CART_VERSION_MISMATCH");
            });
    }

    @Test
    void rejectsFulfillmentForExpiredSession() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var service = new OrderSessionService(sessionRepository, mock(StoreRepository.class), 30);
        var session = new OrderSession(store(), OffsetDateTime.now().minusSeconds(1));
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> service.selectFulfillment(session.getId(), 0, FulfillmentType.DINE_IN))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.GONE);
                assertThat(exception.code()).isEqualTo("ORDER_SESSION_EXPIRED");
            });
    }

    private Store store() {
        return new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    }
}
