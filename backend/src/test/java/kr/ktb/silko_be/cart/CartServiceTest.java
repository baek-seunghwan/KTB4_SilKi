package kr.ktb.silko_be.cart;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuCategory;
import kr.ktb.silko_be.menu.MenuOptionGroup;
import kr.ktb.silko_be.menu.MenuOptionGroupRepository;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;

class CartServiceTest {
    @Test
    void returnsItemsForActiveSession() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var service = service(sessionRepository, cartItemRepository);
        var session = session(OffsetDateTime.now().plusMinutes(30));
        when(sessionRepository.findById(session.getId())).thenReturn(Optional.of(session));
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(List.of());

        var snapshot = service.get(session.getId());

        assertThat(snapshot.session()).isEqualTo(session);
        assertThat(snapshot.items()).isEmpty();
    }

    @Test
    void rejectsExpiredSession() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var service = service(sessionRepository, mock(CartItemRepository.class));
        var session = session(OffsetDateTime.now().minusSeconds(1));
        when(sessionRepository.findById(session.getId())).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> service.get(session.getId()))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.GONE);
                assertThat(exception.code()).isEqualTo("ORDER_SESSION_EXPIRED");
            });
    }

    @Test
    void addsMenuWithRequestedAndDefaultOptionsThenIncrementsVersion() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var menuRepository = mock(MenuRepository.class);
        var optionGroupRepository = mock(MenuOptionGroupRepository.class);
        var service = new CartService(sessionRepository, cartItemRepository, menuRepository, optionGroupRepository);
        var store = store();
        var session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
        var menu = new Menu(store, MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼", 4500, null);
        var temperature = new MenuOptionGroup(menu, "TEMPERATURE", "온도", true, 1, 1, 0);
        temperature.addValue("HOT", "따뜻하게", 0, false, 0);
        var ice = temperature.addValue("ICE", "차갑게", 0, false, 1);
        var size = new MenuOptionGroup(menu, "SIZE", "사이즈", true, 1, 1, 1);
        var regular = size.addValue("REGULAR", "레귤러", 0, true, 0);
        size.addValue("LARGE", "라지", 500, false, 1);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(menuRepository.findByIdAndStoreId(menu.getId(), store.getId())).thenReturn(Optional.of(menu));
        when(optionGroupRepository.findAllByMenu_IdOrderByDisplayOrderAsc(menu.getId()))
            .thenReturn(List.of(temperature, size));
        when(cartItemRepository.saveAndFlush(any())).thenAnswer(invocation -> invocation.getArgument(0));
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(List.of());

        service.add(session.getId(), 0, menu.getId(), 2, List.of(ice.getId()));

        var itemCaptor = ArgumentCaptor.forClass(CartItem.class);
        org.mockito.Mockito.verify(cartItemRepository).saveAndFlush(itemCaptor.capture());
        assertThat(itemCaptor.getValue().getSelectedOptions())
            .extracting(option -> option.getId())
            .containsExactlyInAnyOrder(ice.getId(), regular.getId());
        assertThat(session.getCartVersion()).isEqualTo(1);
    }

    @Test
    void rejectsStaleCartVersionBeforeAddingMenu() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var service = service(sessionRepository, cartItemRepository);
        var session = session(OffsetDateTime.now().plusMinutes(30));
        session.incrementCartVersion();
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> service.add(session.getId(), 0, java.util.UUID.randomUUID(), 1, List.of()))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.CONFLICT);
                assertThat(exception.code()).isEqualTo("CART_VERSION_MISMATCH");
            });
    }

    @Test
    void replacesTheWholeCartAndIncrementsVersionOnce() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var menuRepository = mock(MenuRepository.class);
        var optionGroupRepository = mock(MenuOptionGroupRepository.class);
        var service = new CartService(sessionRepository, cartItemRepository, menuRepository, optionGroupRepository);
        var store = store();
        var session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
        var previousMenu = new Menu(store, MenuCategory.COFFEE, "기존 메뉴", "", 3000, null);
        var previousItem = new CartItem(session, previousMenu, 1);
        var nextMenu = new Menu(store, MenuCategory.COFFEE, "새 메뉴", "", 4000, null);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(menuRepository.findAllByStoreIdAndIdIn(store.getId(), java.util.Set.of(nextMenu.getId())))
            .thenReturn(List.of(nextMenu));
        when(optionGroupRepository.findAllByMenu_IdInOrderByDisplayOrderAsc(java.util.Set.of(nextMenu.getId())))
            .thenReturn(List.of());
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(List.of(previousItem), List.of());

        service.replace(session.getId(), 0,
            List.of(new CartService.Replacement(nextMenu.getId(), 2, List.of())));

        verify(cartItemRepository).deleteAll(List.of(previousItem));
        verify(cartItemRepository).saveAllAndFlush(any());
        assertThat(session.getCartVersion()).isEqualTo(1);
    }

    @Test
    void validatesTheWholeReplacementBeforeDeletingCurrentItems() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var menuRepository = mock(MenuRepository.class);
        var service = new CartService(sessionRepository, cartItemRepository, menuRepository,
            mock(MenuOptionGroupRepository.class));
        var session = session(OffsetDateTime.now().plusMinutes(30));
        var missingMenuId = java.util.UUID.randomUUID();
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(menuRepository.findAllByStoreIdAndIdIn(session.getStoreId(), java.util.Set.of(missingMenuId)))
            .thenReturn(List.of());

        assertThatThrownBy(() -> service.replace(session.getId(), 0,
            List.of(new CartService.Replacement(missingMenuId, 1, List.of()))))
            .isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.code()).isEqualTo("MENU_NOT_FOUND"));
        verify(cartItemRepository, never()).deleteAll(any());
    }

    @Test
    void updatesQuantityAndReplacesOptionsThenIncrementsVersion() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var optionGroupRepository = mock(MenuOptionGroupRepository.class);
        var service = new CartService(sessionRepository, cartItemRepository,
            mock(MenuRepository.class), optionGroupRepository);
        var store = store();
        var session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
        var menu = new Menu(store, MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼", 4500, null);
        var temperature = new MenuOptionGroup(menu, "TEMPERATURE", "온도", true, 1, 1, 0);
        var hot = temperature.addValue("HOT", "따뜻하게", 0, false, 0);
        var ice = temperature.addValue("ICE", "차갑게", 0, false, 1);
        var item = new CartItem(session, menu, 1);
        item.addOption(hot);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(cartItemRepository.findByIdAndOrderSession_Id(item.getId(), session.getId()))
            .thenReturn(Optional.of(item));
        when(optionGroupRepository.findAllByMenu_IdOrderByDisplayOrderAsc(menu.getId()))
            .thenReturn(List.of(temperature));
        when(cartItemRepository.saveAndFlush(item)).thenReturn(item);
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(List.of(item));

        var snapshot = service.update(session.getId(), item.getId(), 0, 3, List.of(ice.getId()));

        assertThat(item.getQuantity()).isEqualTo(3);
        assertThat(item.getSelectedOptions()).extracting(option -> option.getId())
            .containsExactly(ice.getId());
        assertThat(snapshot.session().getCartVersion()).isEqualTo(1);
    }

    @Test
    void deletesOnlyItemBelongingToSessionThenIncrementsVersion() {
        var sessionRepository = mock(OrderSessionRepository.class);
        var cartItemRepository = mock(CartItemRepository.class);
        var service = service(sessionRepository, cartItemRepository);
        var store = store();
        var session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
        var menu = new Menu(store, MenuCategory.COFFEE, "아메리카노", "깔끔한 커피", 4000, null);
        var item = new CartItem(session, menu, 1);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(cartItemRepository.findByIdAndOrderSession_Id(item.getId(), session.getId()))
            .thenReturn(Optional.of(item));
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(List.of());

        var snapshot = service.delete(session.getId(), item.getId(), 0);

        verify(cartItemRepository).delete(item);
        assertThat(snapshot.items()).isEmpty();
        assertThat(snapshot.session().getCartVersion()).isEqualTo(1);
    }

    private CartService service(OrderSessionRepository sessionRepository,
                                CartItemRepository cartItemRepository) {
        return new CartService(sessionRepository, cartItemRepository,
            mock(MenuRepository.class), mock(MenuOptionGroupRepository.class));
    }

    private OrderSession session(OffsetDateTime expiresAt) {
        return new OrderSession(store(), expiresAt);
    }

    private Store store() {
        return new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    }
}
