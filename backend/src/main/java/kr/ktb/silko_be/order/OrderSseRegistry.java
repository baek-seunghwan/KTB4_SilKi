package kr.ktb.silko_be.order;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Supplier;
import kr.ktb.silko_be.order.OrderDtos.OrderResponse;
import kr.ktb.silko_be.order.OrderDtos.OrderStatusResponse;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class OrderSseRegistry {
    private static final long TIMEOUT = 30L * 60 * 1000;
    private final Map<UUID, CopyOnWriteArrayList<SseEmitter>> storeEmitters = new ConcurrentHashMap<>();
    private final Map<UUID, CopyOnWriteArrayList<SseEmitter>> orderEmitters = new ConcurrentHashMap<>();
    private final Supplier<SseEmitter> emitterFactory;

    public OrderSseRegistry() {
        this(() -> new SseEmitter(TIMEOUT));
    }

    OrderSseRegistry(Supplier<SseEmitter> emitterFactory) {
        this.emitterFactory = emitterFactory;
    }

    public SseEmitter subscribeStore(UUID storeId) {
        return subscribe(storeEmitters, storeId);
    }

    public SseEmitter subscribeOrder(UUID orderId) {
        return subscribe(orderEmitters, orderId);
    }

    public void orderCreated(UUID storeId, OrderResponse order) {
        send(storeEmitters, storeId, "ORDER_CREATED", order, false);
    }

    public void statusChanged(OrderStatusResponse status) {
        send(orderEmitters, status.id(), "ORDER_STATUS_CHANGED", status, false);
        if (status.pickupReady()) {
            send(orderEmitters, status.id(), "PICKUP_READY", status, true);
        }
    }

    @Scheduled(fixedRate = 20_000)
    void heartbeat() {
        storeEmitters.keySet().forEach(id -> send(storeEmitters, id, "HEARTBEAT", Map.of(), false));
        orderEmitters.keySet().forEach(id -> send(orderEmitters, id, "HEARTBEAT", Map.of(), false));
    }

    private SseEmitter subscribe(Map<UUID, CopyOnWriteArrayList<SseEmitter>> registry, UUID id) {
        var emitter = emitterFactory.get();
        registry.computeIfAbsent(id, ignored -> new CopyOnWriteArrayList<>()).add(emitter);
        Runnable remove = () -> remove(registry, id, emitter);
        emitter.onCompletion(remove);
        emitter.onTimeout(remove);
        emitter.onError(ignored -> remove.run());
        return emitter;
    }

    private void send(Map<UUID, CopyOnWriteArrayList<SseEmitter>> registry, UUID id,
                      String event, Object data, boolean complete) {
        var emitters = registry.get(id);
        if (emitters == null) return;
        for (var emitter : emitters) {
            try {
                emitter.send(SseEmitter.event().name(event).data(data));
                if (complete) emitter.complete();
            } catch (IOException | IllegalStateException exception) {
                emitter.complete();
            }
        }
    }

    private void remove(Map<UUID, CopyOnWriteArrayList<SseEmitter>> registry, UUID id, SseEmitter emitter) {
        var emitters = registry.get(id);
        if (emitters == null) return;
        emitters.remove(emitter);
        if (emitters.isEmpty()) registry.remove(id, emitters);
    }
}
