package kr.ktb.silko_be.cart;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.menu.MenuOptionValue;
import kr.ktb.silko_be.menu.SalesStatus;
import kr.ktb.silko_be.session.FulfillmentType;
import kr.ktb.silko_be.storage.ImageStorage;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/v1/order-sessions/{sessionId}/cart")
public class CartController {
    private final CartService service;
    private final ImageStorage imageStorage;

    public CartController(CartService service, ImageStorage imageStorage) {
        this.service = service;
        this.imageStorage = imageStorage;
    }

    @GetMapping
    public CartResponse get(@PathVariable UUID sessionId) {
        return response(service.get(sessionId));
    }

    @PostMapping("/items")
    @ResponseStatus(HttpStatus.CREATED)
    public CartResponse add(@PathVariable UUID sessionId,
                            @RequestHeader("If-Match") @Min(0) long expectedCartVersion,
                            @Valid @RequestBody AddCartItemRequest body) {
        return response(service.add(
            sessionId,
            expectedCartVersion,
            body.menuId(),
            body.quantity(),
            body.optionValueIds()
        ));
    }

    @PutMapping
    public CartResponse replace(@PathVariable UUID sessionId,
                                @RequestHeader("If-Match") @Min(0) long expectedCartVersion,
                                @Valid @RequestBody ReplaceCartRequest body) {
        return response(service.replace(
            sessionId,
            expectedCartVersion,
            body.items().stream()
                .map(item -> new CartService.Replacement(item.menuId(), item.quantity(), item.optionValueIds()))
                .toList()
        ));
    }

    @PatchMapping("/items/{cartItemId}")
    public CartResponse update(@PathVariable UUID sessionId,
                               @PathVariable UUID cartItemId,
                               @RequestHeader("If-Match") @Min(0) long expectedCartVersion,
                               @Valid @RequestBody UpdateCartItemRequest body) {
        return response(service.update(
            sessionId,
            cartItemId,
            expectedCartVersion,
            body.quantity(),
            body.optionValueIds()
        ));
    }

    @DeleteMapping("/items/{cartItemId}")
    public CartResponse delete(@PathVariable UUID sessionId,
                               @PathVariable UUID cartItemId,
                               @RequestHeader("If-Match") @Min(0) long expectedCartVersion) {
        return response(service.delete(sessionId, cartItemId, expectedCartVersion));
    }

    private CartResponse response(CartService.CartSnapshot snapshot) {
        var items = snapshot.items().stream().map(this::itemResponse).toList();
        int totalQuantity = items.stream().mapToInt(CartItemResponse::quantity).sum();
        long totalPrice = items.stream().mapToLong(CartItemResponse::totalPrice).sum();
        return new CartResponse(snapshot.session().getId(), snapshot.session().getCartVersion(),
            snapshot.session().getFulfillmentType(), items, totalQuantity, totalPrice);
    }

    private CartItemResponse itemResponse(CartItem item) {
        var menu = item.getMenu();
        var options = item.getSelectedOptions().stream().map(OptionResponse::from).toList();
        long optionPrice = options.stream().mapToLong(OptionResponse::additionalPrice).sum();
        long unitPrice = menu.getPrice() + optionPrice;
        return new CartItemResponse(
            item.getId(),
            menu.getId(),
            menu.getName(),
            menu.getDescription(),
            imageStorage.url(menu.getImageKey()),
            menu.getSalesStatus() == SalesStatus.AVAILABLE,
            item.getQuantity(),
            menu.getPrice(),
            options,
            unitPrice,
            unitPrice * item.getQuantity()
        );
    }

    public record CartResponse(UUID sessionId, long cartVersion, FulfillmentType fulfillmentType,
                               List<CartItemResponse> items, int totalQuantity, long totalPrice) {}

    public record AddCartItemRequest(@NotNull UUID menuId,
                                     @Min(1) @Max(20) int quantity,
                                     @NotNull @Size(max = 20) List<@NotNull UUID> optionValueIds) {}

    public record UpdateCartItemRequest(@Min(1) @Max(20) int quantity,
                                        @NotNull @Size(max = 20) List<@NotNull UUID> optionValueIds) {}

    public record ReplaceCartRequest(
        @NotEmpty @Size(max = 20) List<@Valid ReplaceCartItemRequest> items
    ) {}

    public record ReplaceCartItemRequest(@NotNull UUID menuId,
                                         @Min(1) @Max(20) int quantity,
                                         @NotNull @Size(max = 20) List<@NotNull UUID> optionValueIds) {}

    public record CartItemResponse(UUID cartItemId, UUID menuId, String menuName, String description,
                                   String imageUrl, boolean available, int quantity, long basePrice,
                                   List<OptionResponse> options, long unitPrice, long totalPrice) {}

    public record OptionResponse(UUID optionValueId, UUID optionGroupId, String optionGroupCode,
                                 String optionGroupName, String code, String name, long additionalPrice) {
        static OptionResponse from(MenuOptionValue option) {
            return new OptionResponse(
                option.getId(),
                option.getOptionGroupId(),
                option.getOptionGroupCode(),
                option.getOptionGroupName(),
                option.getCode(),
                option.getName(),
                option.getAdditionalPrice()
            );
        }
    }
}
