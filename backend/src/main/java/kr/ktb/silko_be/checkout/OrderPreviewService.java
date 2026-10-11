package kr.ktb.silko_be.checkout;

import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import kr.ktb.silko_be.cart.CartItem;
import kr.ktb.silko_be.cart.CartItemRepository;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuOptionGroup;
import kr.ktb.silko_be.menu.MenuOptionGroupRepository;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.menu.SalesStatus;
import kr.ktb.silko_be.session.FulfillmentType;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.session.OrderSessionStatus;
import kr.ktb.silko_be.store.OperatingStatus;
import kr.ktb.silko_be.store.StoreRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPreviewService {
    private final OrderSessionRepository sessionRepository;
    private final StoreRepository storeRepository;
    private final CartItemRepository cartItemRepository;
    private final MenuRepository menuRepository;
    private final MenuOptionGroupRepository optionGroupRepository;

    public OrderPreviewService(OrderSessionRepository sessionRepository,
                               StoreRepository storeRepository,
                               CartItemRepository cartItemRepository,
                               MenuRepository menuRepository,
                               MenuOptionGroupRepository optionGroupRepository) {
        this.sessionRepository = sessionRepository;
        this.storeRepository = storeRepository;
        this.cartItemRepository = cartItemRepository;
        this.menuRepository = menuRepository;
        this.optionGroupRepository = optionGroupRepository;
    }

    @Transactional
    public OrderPreview preview(UUID sessionId, long expectedCartVersion) {
        var session = sessionRepository.findByIdForUpdate(sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_SESSION_NOT_FOUND",
                "주문 세션을 찾을 수 없습니다."));
        return validate(session, expectedCartVersion).preview();
    }

    public ValidatedOrder validate(OrderSession session, long expectedCartVersion) {
        validateSession(session, expectedCartVersion);
        var store = storeRepository.findByIdForUpdate(session.getStoreId())
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "STORE_NOT_FOUND",
                "매장을 찾을 수 없습니다."));
        if (store.getOperatingStatus() != OperatingStatus.OPEN) {
            throw new ApiException(HttpStatus.CONFLICT, "STORE_CLOSED", "현재 영업이 종료되어 주문할 수 없습니다.");
        }
        if (session.getFulfillmentType() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "FULFILLMENT_REQUIRED", "매장 또는 포장을 선택해주세요.");
        }

        var cartItems = cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId());
        if (cartItems.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "CART_EMPTY", "장바구니가 비어 있습니다.");
        }

        var menuIds = cartItems.stream().map(item -> item.getMenu().getId()).collect(Collectors.toSet());
        var menus = menuRepository.findAllByStoreIdAndIdIn(session.getStoreId(), menuIds).stream()
            .collect(Collectors.toMap(Menu::getId, Function.identity()));
        if (menus.size() != menuIds.size()) {
            throw new ApiException(HttpStatus.CONFLICT, "CART_INVALID", "주문할 수 없는 메뉴가 포함되어 있습니다.");
        }
        validateTotalQuantities(cartItems);

        var optionGroups = optionGroupRepository.findAllByMenu_IdInOrderByDisplayOrderAsc(menuIds).stream()
            .collect(Collectors.groupingBy(MenuOptionGroup::getMenuId));
        var items = cartItems.stream()
            .map(item -> previewItem(item, menus.get(item.getMenu().getId()),
                optionGroups.getOrDefault(item.getMenu().getId(), List.of())))
            .toList();
        int totalQuantity = items.stream().mapToInt(PreviewItem::quantity).sum();
        long totalPrice = items.stream().mapToLong(PreviewItem::totalPrice).sum();

        var preview = new OrderPreview(
            session.getId(),
            session.getStoreId(),
            session.getCartVersion(),
            session.getFulfillmentType(),
            items,
            totalQuantity,
            totalPrice,
            OffsetDateTime.now()
        );
        return new ValidatedOrder(session, store, preview);
    }

    private void validateSession(OrderSession session, long expectedCartVersion) {
        if (session.getStatus() == OrderSessionStatus.EXPIRED
            || !session.getExpiresAt().isAfter(OffsetDateTime.now())) {
            throw new ApiException(HttpStatus.GONE, "ORDER_SESSION_EXPIRED", "주문 세션이 만료되었습니다.");
        }
        if (session.getStatus() != OrderSessionStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "ORDER_SESSION_NOT_ACTIVE",
                "이미 주문이 완료된 세션입니다.");
        }
        if (session.getCartVersion() != expectedCartVersion) {
            throw new ApiException(HttpStatus.CONFLICT, "CART_VERSION_MISMATCH",
                "주문 정보가 변경되었습니다. 현재 버전은 " + session.getCartVersion() + "입니다.");
        }
    }

    private void validateTotalQuantities(List<CartItem> items) {
        Map<UUID, Integer> quantities = items.stream().collect(Collectors.groupingBy(
            item -> item.getMenu().getId(),
            Collectors.summingInt(CartItem::getQuantity)
        ));
        if (quantities.values().stream().anyMatch(quantity -> quantity > 20)) {
            throw new ApiException(HttpStatus.CONFLICT, "INVALID_QUANTITY", "메뉴별 수량은 20개 이하여야 합니다.");
        }
    }

    private PreviewItem previewItem(CartItem item, Menu menu, List<MenuOptionGroup> groups) {
        if (menu.getSalesStatus() != SalesStatus.AVAILABLE) {
            throw new ApiException(HttpStatus.CONFLICT, "MENU_SOLD_OUT", menu.getName() + "은(는) 품절입니다.");
        }
        validateOptions(item, groups);

        var options = item.getSelectedOptions().stream()
            .map(option -> new PreviewOption(
                option.getId(), option.getOptionGroupId(), option.getOptionGroupCode(),
                option.getOptionGroupName(), option.getCode(), option.getName(), option.getAdditionalPrice()
            ))
            .toList();
        long optionPrice = options.stream().mapToLong(PreviewOption::additionalPrice).sum();
        long unitPrice = Math.addExact(menu.getPrice(), optionPrice);
        long totalPrice = Math.multiplyExact(unitPrice, item.getQuantity());
        return new PreviewItem(
            item.getId(), menu.getId(), menu.getName(), item.getQuantity(), menu.getPrice(),
            options, unitPrice, totalPrice
        );
    }

    private void validateOptions(CartItem item, List<MenuOptionGroup> groups) {
        Set<UUID> selectedIds = item.getSelectedOptions().stream()
            .map(option -> option.getId())
            .collect(Collectors.toSet());
        Set<UUID> allowedIds = groups.stream()
            .map(MenuOptionGroup::getValues)
            .flatMap(Collection::stream)
            .map(option -> option.getId())
            .collect(Collectors.toSet());
        if (!allowedIds.containsAll(selectedIds)) {
            throw invalidOptions(item);
        }
        for (var group : groups) {
            long selectedCount = group.getValues().stream()
                .filter(option -> selectedIds.contains(option.getId()))
                .count();
            int minimumSelections = group.isRequired() ? Math.max(1, group.getMinSelections())
                : group.getMinSelections();
            if (selectedCount < minimumSelections || selectedCount > group.getMaxSelections()) {
                throw invalidOptions(item);
            }
        }
    }

    private ApiException invalidOptions(CartItem item) {
        return new ApiException(HttpStatus.CONFLICT, "CART_OPTIONS_INVALID",
            item.getMenu().getName() + "의 옵션을 다시 선택해주세요.");
    }

    public record OrderPreview(UUID sessionId, UUID storeId, long cartVersion,
                               FulfillmentType fulfillmentType,
                               List<PreviewItem> items, int totalQuantity, long totalPrice,
                               OffsetDateTime validatedAt) {}

    public record ValidatedOrder(OrderSession session, kr.ktb.silko_be.store.Store store,
                                 OrderPreview preview) {}

    public record PreviewItem(UUID cartItemId, UUID menuId, String menuName, int quantity,
                              long basePrice, List<PreviewOption> options,
                              long unitPrice, long totalPrice) {}

    public record PreviewOption(UUID optionValueId, UUID optionGroupId, String optionGroupCode,
                                String optionGroupName, String code, String name,
                                long additionalPrice) {}
}
