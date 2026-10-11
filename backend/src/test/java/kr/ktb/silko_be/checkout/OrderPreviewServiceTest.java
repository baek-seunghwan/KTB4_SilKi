package kr.ktb.silko_be.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.cart.CartItem;
import kr.ktb.silko_be.cart.CartItemRepository;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuCategory;
import kr.ktb.silko_be.menu.MenuOptionGroup;
import kr.ktb.silko_be.menu.MenuOptionGroupRepository;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.menu.SalesStatus;
import kr.ktb.silko_be.session.FulfillmentType;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class OrderPreviewServiceTest {
    private final OrderSessionRepository sessionRepository = mock(OrderSessionRepository.class);
    private final StoreRepository storeRepository = mock(StoreRepository.class);
    private final CartItemRepository cartItemRepository = mock(CartItemRepository.class);
    private final MenuRepository menuRepository = mock(MenuRepository.class);
    private final MenuOptionGroupRepository optionGroupRepository = mock(MenuOptionGroupRepository.class);
    private final OrderPreviewService service = new OrderPreviewService(
        sessionRepository, storeRepository, cartItemRepository, menuRepository, optionGroupRepository
    );
    private final Store store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    private final OrderSession session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
    private final Menu menu = new Menu(store, MenuCategory.COFFEE, "카페 라떼", "부드러운 라떼", 4500, null);

    @BeforeEach
    void setUp() {
        session.selectFulfillment(FulfillmentType.TAKEOUT);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(storeRepository.findByIdForUpdate(store.getId())).thenReturn(Optional.of(store));
    }

    @Test
    void returnsAuthoritativePreviewAfterFinalValidation() {
        var size = new MenuOptionGroup(menu, "SIZE", "사이즈", true, 1, 1, 0);
        var large = size.addValue("LARGE", "라지", 500, false, 0);
        var item = new CartItem(session, menu, 2);
        item.addOption(large);
        prepareCart(List.of(item), List.of(size));

        var preview = service.preview(session.getId(), 1);

        assertThat(preview.fulfillmentType()).isEqualTo(FulfillmentType.TAKEOUT);
        assertThat(preview.cartVersion()).isEqualTo(1);
        assertThat(preview.totalQuantity()).isEqualTo(2);
        assertThat(preview.totalPrice()).isEqualTo(10_000);
        assertThat(preview.items().getFirst().unitPrice()).isEqualTo(5_000);
        assertThat(preview.items().getFirst().options().getFirst().code()).isEqualTo("LARGE");
        assertThat(preview.validatedAt()).isNotNull();
    }

    @Test
    void rejectsPreviewBeforeFulfillmentSelection() {
        var unselectedSession = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));
        when(sessionRepository.findByIdForUpdate(unselectedSession.getId()))
            .thenReturn(Optional.of(unselectedSession));

        assertApiError(
            () -> service.preview(unselectedSession.getId(), 0),
            HttpStatus.CONFLICT,
            "FULFILLMENT_REQUIRED"
        );
    }

    @Test
    void rejectsEmptyCart() {
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(List.of());

        assertApiError(() -> service.preview(session.getId(), 1), HttpStatus.CONFLICT, "CART_EMPTY");
    }

    @Test
    void rejectsSoldOutMenu() {
        var item = new CartItem(session, menu, 1);
        menu.changeSalesStatus(SalesStatus.SOLD_OUT);
        prepareCart(List.of(item), List.of());

        assertApiError(() -> service.preview(session.getId(), 1), HttpStatus.CONFLICT, "MENU_SOLD_OUT");
    }

    @Test
    void rejectsMissingRequiredOption() {
        var temperature = new MenuOptionGroup(menu, "TEMPERATURE", "온도", true, 1, 1, 0);
        temperature.addValue("HOT", "따뜻하게", 0, false, 0);
        var item = new CartItem(session, menu, 1);
        prepareCart(List.of(item), List.of(temperature));

        assertApiError(
            () -> service.preview(session.getId(), 1),
            HttpStatus.CONFLICT,
            "CART_OPTIONS_INVALID"
        );
    }

    @Test
    void rejectsCombinedQuantityOverMenuLimit() {
        var first = new CartItem(session, menu, 11);
        var second = new CartItem(session, menu, 10);
        prepareCart(List.of(first, second), List.of());

        assertApiError(() -> service.preview(session.getId(), 1), HttpStatus.CONFLICT, "INVALID_QUANTITY");
    }

    @Test
    void rejectsStaleCartVersion() {
        assertApiError(
            () -> service.preview(session.getId(), 0),
            HttpStatus.CONFLICT,
            "CART_VERSION_MISMATCH"
        );
    }

    private void prepareCart(List<CartItem> items, List<MenuOptionGroup> groups) {
        when(cartItemRepository.findAllByOrderSession_IdOrderByCreatedAtAsc(session.getId()))
            .thenReturn(items);
        when(menuRepository.findAllByStoreIdAndIdIn(store.getId(), Set.of(menu.getId())))
            .thenReturn(List.of(menu));
        when(optionGroupRepository.findAllByMenu_IdInOrderByDisplayOrderAsc(Set.of(menu.getId())))
            .thenReturn(groups);
    }

    private void assertApiError(Runnable action, HttpStatus status, String code) {
        assertThatThrownBy(action::run)
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(status);
                assertThat(exception.code()).isEqualTo(code);
            });
    }
}
