package kr.ktb.silko_be.order;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.checkout.OrderPreviewService;
import kr.ktb.silko_be.checkout.OrderPreviewService.PreviewOption;
import kr.ktb.silko_be.menu.DrinkOptions.Choice;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.menu.SalesStatus;
import kr.ktb.silko_be.menu.DrinkOptions.DrinkSize;
import kr.ktb.silko_be.menu.DrinkOptions.ExtraShot;
import kr.ktb.silko_be.menu.DrinkOptions.SweetnessAdjustment;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.menu.DrinkOptions.OptionType;
import kr.ktb.silko_be.order.OrderDtos.OrderCreateRequest;
import kr.ktb.silko_be.order.OrderDtos.OrderItemResponse;
import kr.ktb.silko_be.order.OrderDtos.OrderOptionResponse;
import kr.ktb.silko_be.order.OrderDtos.OrderResponse;
import kr.ktb.silko_be.order.OrderDtos.OrderStatusResponse;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.store.OperatingStatus;
import kr.ktb.silko_be.store.StoreRepository;
import kr.ktb.silko_be.store.StoreService;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final MenuRepository menuRepository;
    private final StoreRepository storeRepository;
    private final StoreService storeService;
    private final OrderSseRegistry sse;
    private final OrderSessionRepository sessionRepository;
    private final OrderPreviewService previewService;

    public OrderService(OrderRepository orderRepository, MenuRepository menuRepository,
                        StoreRepository storeRepository, StoreService storeService, OrderSseRegistry sse,
                        OrderSessionRepository sessionRepository, OrderPreviewService previewService) {
        this.orderRepository = orderRepository;
        this.menuRepository = menuRepository;
        this.storeRepository = storeRepository;
        this.storeService = storeService;
        this.sse = sse;
        this.sessionRepository = sessionRepository;
        this.previewService = previewService;
    }

    @Transactional
    public OrderResponse checkout(UUID sessionId, long expectedCartVersion, String idempotencyKey) {
        idempotencyKey = idempotencyKey.trim();
        var session = sessionRepository.findByIdForUpdate(sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_SESSION_NOT_FOUND",
                "주문 세션을 찾을 수 없습니다."));

        var existingForSession = orderRepository.findByOrderSessionId(sessionId);
        if (existingForSession.isPresent()) {
            var existing = existingForSession.get();
            if (!existing.getIdempotencyKey().equals(idempotencyKey)) {
                throw new ApiException(HttpStatus.CONFLICT, "ORDER_SESSION_ALREADY_ORDERED",
                    "이미 주문이 완료된 세션입니다.");
            }
            return response(existing);
        }

        var validated = previewService.validate(session, expectedCartVersion);
        var preview = validated.preview();
        var reusedKey = orderRepository.findByStoreIdAndIdempotencyKey(preview.storeId(), idempotencyKey);
        if (reusedKey.isPresent()) {
            throw new ApiException(HttpStatus.CONFLICT, "IDEMPOTENCY_KEY_REUSED",
                "다른 주문에서 사용한 Idempotency-Key입니다.");
        }

        var order = new CustomerOrder(
            validated.store(),
            orderRepository.nextOrderNumber(),
            idempotencyKey,
            sessionId,
            preview.fulfillmentType(),
            PaymentMethod.PAY_AT_COUNTER
        );
        preview.items().forEach(item -> {
            var choices = item.options().stream().map(this::snapshotChoice).toArray(Choice[]::new);
            order.addItem(item.menuId(), item.menuName(), item.basePrice(), item.quantity(), null, choices);
        });

        var savedOrder = orderRepository.saveAndFlush(order);
        session.markOrdered();
        sessionRepository.flush();
        var response = response(savedOrder);
        afterCommit(() -> sse.orderCreated(preview.storeId(), response));
        return response;
    }

    @Transactional
    public OrderResponse create(UUID storeId, String idempotencyKey, OrderCreateRequest request) {
        idempotencyKey = idempotencyKey.trim();
        var store = storeRepository.findByIdForUpdate(storeId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "STORE_NOT_FOUND", "매장을 찾을 수 없습니다."));
        if (store.getOperatingStatus() != OperatingStatus.OPEN) {
            throw new ApiException(HttpStatus.CONFLICT, "STORE_CLOSED", "현재 영업이 종료되어 주문할 수 없습니다.");
        }

        var existing = orderRepository.findByStoreIdAndIdempotencyKey(storeId, idempotencyKey);
        if (existing.isPresent()) return response(existing.get());

        var totalQuantities = new LinkedHashMap<UUID, Integer>();
        var selections = new LinkedHashMap<ItemKey, Integer>();
        request.items().forEach(item -> {
            totalQuantities.merge(item.menuId(), item.quantity(), Integer::sum);
            var options = item.options();
            selections.merge(new ItemKey(item.menuId(), options.temperature(), options.size(),
                options.extraShot(), options.sweetness()), item.quantity(), Integer::sum);
        });
        if (totalQuantities.values().stream().anyMatch(quantity -> quantity > 20)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_QUANTITY", "메뉴별 수량은 20개 이하여야 합니다.");
        }

        var menus = menuRepository.findAllByStoreIdAndIdIn(storeId, totalQuantities.keySet()).stream()
            .collect(Collectors.toMap(Menu::getId, Function.identity()));
        if (menus.size() != totalQuantities.size()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "MENU_NOT_FOUND", "메뉴를 찾을 수 없습니다.");
        }

        var order = new CustomerOrder(store, orderRepository.nextOrderNumber(), idempotencyKey);
        selections.forEach((selection, quantity) -> {
            var menu = menus.get(selection.menuId());
            if (menu.getSalesStatus() != SalesStatus.AVAILABLE) {
                throw new ApiException(HttpStatus.CONFLICT, "MENU_SOLD_OUT", menu.getName() + "은(는) 품절입니다.");
            }
            if (!menu.supports(selection.temperature())) {
                throw new ApiException(HttpStatus.CONFLICT, "MENU_OPTION_NOT_AVAILABLE",
                    menu.getName() + "에서 선택할 수 없는 온도입니다.");
            }
            if (!menu.isExtraShotAvailable() && selection.extraShot() != ExtraShot.NONE) {
                throw new ApiException(HttpStatus.CONFLICT, "MENU_OPTION_NOT_AVAILABLE",
                    menu.getName() + "에는 샷을 추가할 수 없습니다.");
            }
            var finalSweetness = menu.getDefaultSweetness().adjust(selection.sweetness());
            order.addItem(selection.menuId(), menu.getName(), menu.getPrice(), quantity, finalSweetness,
                selection.temperature(), selection.size(), selection.extraShot(), selection.sweetness());
        });
        var savedOrder = orderRepository.saveAndFlush(order);
        var response = response(savedOrder);
        afterCommit(() -> sse.orderCreated(storeId, response));
        return response;
    }

    @Transactional(readOnly = true)
    public OrderResponse get(UUID orderId) {
        return response(requireOrder(orderId));
    }

    @Transactional(readOnly = true)
    public Page<OrderResponse> list(UUID storeId, int page, int size) {
        return list(storeId, null, page, size);
    }

    @Transactional(readOnly = true)
    public Page<OrderResponse> list(UUID storeId, java.util.List<OrderStatus> statuses, int page, int size) {
        storeService.requireManagedStore(storeId);
        var orders = statuses == null || statuses.isEmpty()
            ? orderRepository.findAllByStoreIdInWorkflowOrder(storeId, PageRequest.of(page, size))
            : orderRepository.findAllByStoreIdAndStatusInWorkflowOrder(
                storeId, statuses.stream().map(Enum::name).toList(), PageRequest.of(page, size));
        return orders.map(this::response);
    }

    @Transactional
    public OrderResponse changeStatus(UUID storeId, UUID orderId, OrderStatus next) {
        storeService.requireManagedStore(storeId);
        var order = orderRepository.findByIdAndStoreId(orderId, storeId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", "주문을 찾을 수 없습니다."));
        if (!order.getStatus().canChangeTo(next)) {
            throw new ApiException(HttpStatus.CONFLICT, "INVALID_ORDER_STATUS",
                "현재 상태에서 " + next + "(으)로 변경할 수 없습니다.");
        }
        order.changeStatus(next);
        orderRepository.flush();
        var response = response(order);
        var status = statusResponse(order);
        afterCommit(() -> sse.statusChanged(status));
        return response;
    }

    @Transactional(readOnly = true)
    public void requireOrderExists(UUID orderId) {
        requireOrder(orderId);
    }

    private CustomerOrder requireOrder(UUID orderId) {
        return orderRepository.findById(orderId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", "주문을 찾을 수 없습니다."));
    }

    private OrderResponse response(CustomerOrder order) {
        var items = order.getItems().stream()
            .map(item -> {
                var options = item.getOptions().stream()
                    .sorted(Comparator.comparing(OrderItemOption::getOptionType))
                    .map(option -> new OrderOptionResponse(option.getOptionType(), option.getOptionCode(),
                        option.getOptionName(), option.getAdditionalPrice()))
                    .toList();
                return new OrderItemResponse(item.getMenuName(), item.getQuantity(), item.getBasePrice(),
                    item.getUnitPrice(), item.getSubtotal(), options, item.getFinalSweetness());
            })
            .toList();
        return new OrderResponse(order.getId(), order.getOrderNumber(), order.getStatus(),
            order.getFulfillmentType(), order.getPaymentMethod(), items,
            order.getTotalPrice(), order.getCreatedAt(), order.getUpdatedAt());
    }

    private Choice snapshotChoice(PreviewOption option) {
        try {
            return new SnapshotChoice(
                OptionType.valueOf(option.optionGroupCode().toUpperCase(Locale.ROOT)),
                option.code(),
                option.name(),
                option.additionalPrice()
            );
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "CART_OPTIONS_INVALID",
                "주문에 사용할 수 없는 옵션이 포함되어 있습니다.");
        }
    }

    private OrderStatusResponse statusResponse(CustomerOrder order) {
        var status = order.getStatus();
        return new OrderStatusResponse(order.getId(), order.getOrderNumber(), status,
            order.getFulfillmentType(), status.isPickupReady(), status.getCustomerMessage(), order.getUpdatedAt());
    }

    private void afterCommit(Runnable action) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            action.run();
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                action.run();
            }
        });
    }

    private record ItemKey(UUID menuId, Temperature temperature, DrinkSize size,
                           ExtraShot extraShot, SweetnessAdjustment sweetness) {}

    private record SnapshotChoice(OptionType type, String code, String displayName,
                                  long additionalPrice) implements Choice {}
}
