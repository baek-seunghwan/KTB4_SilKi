package kr.ktb.silko_be.session;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.Test;

class FulfillmentControllerTest {
    @Test
    void returnsSelectedFulfillmentAndCurrentVersion() {
        var service = mock(OrderSessionService.class);
        var session = new OrderSession(
            new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자")),
            OffsetDateTime.now().plusMinutes(30)
        );
        session.selectFulfillment(FulfillmentType.TAKEOUT);
        when(service.selectFulfillment(session.getId(), 0, FulfillmentType.TAKEOUT)).thenReturn(session);

        var response = new FulfillmentController(service).select(
            session.getId(), 0, new FulfillmentController.FulfillmentRequest(FulfillmentType.TAKEOUT)
        );

        assertThat(response.sessionId()).isEqualTo(session.getId());
        assertThat(response.fulfillmentType()).isEqualTo(FulfillmentType.TAKEOUT);
        assertThat(response.cartVersion()).isEqualTo(1);
    }
}
