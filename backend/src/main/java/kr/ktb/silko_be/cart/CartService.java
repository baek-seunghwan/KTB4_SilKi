package kr.ktb.silko_be.cart;

import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.menu.MenuOptionGroup;
import kr.ktb.silko_be.menu.MenuOptionGroupRepository;
import kr.ktb.silko_be.menu.MenuOptionValue;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.menu.SalesStatus;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.session.OrderSessionStatus;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartService {
    private final OrderSessionRepository sessionRepository;
    private final CartItemRepository cartItemRepository;
    private final MenuRepository menuRepository;
    private final MenuOptionGroupRepository optionGroupRepository;

    public CartService(OrderSessionRepository sessionRepository, CartItemRepository cartItemRepository,
                       MenuRepository menuRepository, MenuOptionGroupRepository optionGroupRepository) {
        this.sessionRepository = sessionRepository;
        this.cartItemRepository = cartItemRepository;
        this.menuRepository = menuRepository;
        this.optionGroupRepository = optionGroupRepository;
    }

    @Transactional(readOnly = true)
    public CartSnapshot get(UUID sessionId) {
        var session = sessionRepository.findById(sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_SESSION_NOT_FOUND",
                "주문 세션을 찾을 수 없습니다."));
        validateReadable(session);
        return new CartSnapshot(
            session,
            cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(sessionId)
        );
    }

    @Transactional
    public CartSnapshot add(UUID sessionId, long expectedCartVersion, UUID menuId, int quantity,
                            Collection<UUID> requestedOptionIds) {
        var session = requireMutableSession(sessionId, expectedCartVersion);

        var menu = menuRepository.findByIdAndStoreId(menuId, session.getStoreId())
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "MENU_NOT_FOUND",
                "메뉴를 찾을 수 없습니다."));
        if (menu.getSalesStatus() != SalesStatus.AVAILABLE) {
            throw new ApiException(HttpStatus.CONFLICT, "MENU_SOLD_OUT", menu.getName() + "은(는) 품절입니다.");
        }

        var optionGroups = optionGroupRepository.findAllByMenu_IdOrderByDisplayOrderAsc(menuId);
        var selectedOptions = resolveOptions(optionGroups, requestedOptionIds);
        var item = new CartItem(session, menu, quantity);
        selectedOptions.forEach(item::addOption);
        cartItemRepository.saveAndFlush(item);
        session.incrementCartVersion();
        sessionRepository.flush();

        return snapshot(session);
    }

    @Transactional
    public CartSnapshot replace(UUID sessionId, long expectedCartVersion, List<Replacement> replacements) {
        var session = requireMutableSession(sessionId, expectedCartVersion);
        var totalQuantities = replacements.stream().collect(Collectors.groupingBy(
            Replacement::menuId, Collectors.summingInt(Replacement::quantity)
        ));
        if (totalQuantities.values().stream().anyMatch(quantity -> quantity > 20)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_QUANTITY", "메뉴별 수량은 20개 이하여야 합니다.");
        }
        var menuIds = replacements.stream().map(Replacement::menuId).collect(Collectors.toSet());
        var menus = menuRepository.findAllByStoreIdAndIdIn(session.getStoreId(), menuIds).stream()
            .collect(Collectors.toMap(menu -> menu.getId(), Function.identity()));
        if (menus.size() != menuIds.size()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "MENU_NOT_FOUND", "메뉴를 찾을 수 없습니다.");
        }
        var groupsByMenuId = optionGroupRepository.findAllByMenu_IdInOrderByDisplayOrderAsc(menuIds).stream()
            .collect(Collectors.groupingBy(MenuOptionGroup::getMenuId));
        var nextItems = replacements.stream().map(replacement -> {
            var menu = menus.get(replacement.menuId());
            if (menu.getSalesStatus() != SalesStatus.AVAILABLE) {
                throw new ApiException(HttpStatus.CONFLICT, "MENU_SOLD_OUT",
                    menu.getName() + "은(는) 품절입니다.");
            }
            var item = new CartItem(session, menu, replacement.quantity());
            resolveOptions(groupsByMenuId.getOrDefault(menu.getId(), List.of()), replacement.optionValueIds())
                .forEach(item::addOption);
            return item;
        }).toList();

        var currentItems = cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(sessionId);
        cartItemRepository.deleteAll(currentItems);
        cartItemRepository.flush();
        cartItemRepository.saveAllAndFlush(nextItems);
        session.incrementCartVersion();
        sessionRepository.flush();
        return snapshot(session);
    }

    @Transactional
    public CartSnapshot update(UUID sessionId, UUID cartItemId, long expectedCartVersion,
                               int quantity, Collection<UUID> requestedOptionIds) {
        var session = requireMutableSession(sessionId, expectedCartVersion);
        var item = requireCartItem(sessionId, cartItemId);
        var menu = item.getMenu();
        if (menu.getSalesStatus() != SalesStatus.AVAILABLE) {
            throw new ApiException(HttpStatus.CONFLICT, "MENU_SOLD_OUT", menu.getName() + "은(는) 품절입니다.");
        }

        var optionGroups = optionGroupRepository.findAllByMenu_IdOrderByDisplayOrderAsc(menu.getId());
        item.update(quantity, resolveOptions(optionGroups, requestedOptionIds));
        cartItemRepository.saveAndFlush(item);
        session.incrementCartVersion();
        sessionRepository.flush();

        return snapshot(session);
    }

    @Transactional
    public CartSnapshot delete(UUID sessionId, UUID cartItemId, long expectedCartVersion) {
        var session = requireMutableSession(sessionId, expectedCartVersion);
        var item = requireCartItem(sessionId, cartItemId);
        cartItemRepository.delete(item);
        cartItemRepository.flush();
        session.incrementCartVersion();
        sessionRepository.flush();

        return snapshot(session);
    }

    private LinkedHashSet<MenuOptionValue> resolveOptions(List<MenuOptionGroup> groups,
                                                           Collection<UUID> requestedOptionIds) {
        if (new HashSet<>(requestedOptionIds).size() != requestedOptionIds.size()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_MENU_OPTION", "중복된 옵션이 포함되어 있습니다.");
        }

        Map<UUID, MenuOptionValue> allowedOptions = groups.stream()
            .flatMap(group -> group.getValues().stream())
            .collect(Collectors.toMap(MenuOptionValue::getId, Function.identity()));
        var unknownOptionIds = requestedOptionIds.stream()
            .filter(optionId -> !allowedOptions.containsKey(optionId))
            .toList();
        if (!unknownOptionIds.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_MENU_OPTION",
                "해당 메뉴에서 선택할 수 없는 옵션입니다.");
        }

        var resolved = requestedOptionIds.stream()
            .map(allowedOptions::get)
            .collect(Collectors.toCollection(LinkedHashSet::new));
        for (var group : groups) {
            var selectedForGroup = resolved.stream()
                .filter(option -> option.getOptionGroupId().equals(group.getId()))
                .toList();
            if (selectedForGroup.isEmpty()) {
                var automaticOption = group.getValues().stream()
                    .filter(MenuOptionValue::isDefaultValue)
                    .findFirst()
                    .or(() -> group.getValues().size() == 1
                        ? java.util.Optional.of(group.getValues().getFirst())
                        : java.util.Optional.empty());
                automaticOption.ifPresent(resolved::add);
                selectedForGroup = automaticOption.stream().toList();
            }
            int minimumSelections = group.isRequired() ? Math.max(1, group.getMinSelections())
                : group.getMinSelections();
            if (selectedForGroup.size() < minimumSelections) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "OPTION_REQUIRED",
                    group.getName() + " 옵션을 선택해주세요.");
            }
            if (selectedForGroup.size() > group.getMaxSelections()) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "TOO_MANY_OPTIONS",
                    group.getName() + " 옵션 선택 개수를 확인해주세요.");
            }
        }
        return resolved;
    }

    private void validateCartVersion(OrderSession session, long expectedCartVersion) {
        if (session.getCartVersion() != expectedCartVersion) {
            throw new ApiException(HttpStatus.CONFLICT, "CART_VERSION_MISMATCH",
                "장바구니가 변경되었습니다. 현재 버전은 " + session.getCartVersion() + "입니다.");
        }
    }

    private OrderSession requireMutableSession(UUID sessionId, long expectedCartVersion) {
        var session = sessionRepository.findByIdForUpdate(sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_SESSION_NOT_FOUND",
                "주문 세션을 찾을 수 없습니다."));
        validateReadable(session);
        validateCartVersion(session, expectedCartVersion);
        return session;
    }

    private CartItem requireCartItem(UUID sessionId, UUID cartItemId) {
        return cartItemRepository.findByIdAndOrderSession_Id(cartItemId, sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CART_ITEM_NOT_FOUND",
                "장바구니 항목을 찾을 수 없습니다."));
    }

    private CartSnapshot snapshot(OrderSession session) {
        return new CartSnapshot(
            session,
            cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId())
        );
    }

    private void validateReadable(OrderSession session) {
        if (session.getStatus() == OrderSessionStatus.EXPIRED
            || !session.getExpiresAt().isAfter(OffsetDateTime.now())) {
            throw new ApiException(HttpStatus.GONE, "ORDER_SESSION_EXPIRED", "주문 세션이 만료되었습니다.");
        }
        if (session.getStatus() != OrderSessionStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "ORDER_SESSION_NOT_ACTIVE",
                "이미 주문이 완료된 세션입니다.");
        }
    }

    public record Replacement(UUID menuId, int quantity, List<UUID> optionValueIds) {}
    public record CartSnapshot(OrderSession session, List<CartItem> items) {}
}
