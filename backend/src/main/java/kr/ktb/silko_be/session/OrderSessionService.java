package kr.ktb.silko_be.session;

import java.time.OffsetDateTime;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.store.OperatingStatus;
import kr.ktb.silko_be.store.StoreRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderSessionService {
    private final OrderSessionRepository sessionRepository;
    private final StoreRepository storeRepository;
    private final long ttlMinutes;

    public OrderSessionService(OrderSessionRepository sessionRepository,
                               StoreRepository storeRepository,
                               @Value("${app.order-session.ttl-minutes:30}") long ttlMinutes) {
        this.sessionRepository = sessionRepository;
        this.storeRepository = storeRepository;
        this.ttlMinutes = ttlMinutes;
    }

    @Transactional
    public OrderSession create(UUID storeId) {
        var store = storeRepository.findById(storeId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "STORE_NOT_FOUND", "매장을 찾을 수 없습니다."));
        if (store.getOperatingStatus() != OperatingStatus.OPEN) {
            throw new ApiException(HttpStatus.CONFLICT, "STORE_CLOSED", "현재 영업이 종료되어 주문할 수 없습니다.");
        }

        var expiresAt = OffsetDateTime.now().plusMinutes(ttlMinutes);
        return sessionRepository.saveAndFlush(new OrderSession(store, expiresAt));
    }

    @Transactional
    public OrderSession selectFulfillment(UUID sessionId, long expectedCartVersion,
                                          FulfillmentType fulfillmentType) {
        var session = sessionRepository.findByIdForUpdate(sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_SESSION_NOT_FOUND",
                "주문 세션을 찾을 수 없습니다."));
        validateActive(session);
        if (session.getCartVersion() != expectedCartVersion) {
            throw new ApiException(HttpStatus.CONFLICT, "CART_VERSION_MISMATCH",
                "주문 정보가 변경되었습니다. 현재 버전은 " + session.getCartVersion() + "입니다.");
        }
        if (session.selectFulfillment(fulfillmentType)) {
            sessionRepository.flush();
        }
        return session;
    }

    private void validateActive(OrderSession session) {
        if (session.getStatus() == OrderSessionStatus.EXPIRED
            || !session.getExpiresAt().isAfter(OffsetDateTime.now())) {
            throw new ApiException(HttpStatus.GONE, "ORDER_SESSION_EXPIRED", "주문 세션이 만료되었습니다.");
        }
        if (session.getStatus() != OrderSessionStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "ORDER_SESSION_NOT_ACTIVE",
                "이미 주문이 완료된 세션입니다.");
        }
    }
}
