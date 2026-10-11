package kr.ktb.silko_be.order;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.DrinkSize;
import kr.ktb.silko_be.menu.DrinkOptions.ExtraShot;
import kr.ktb.silko_be.menu.DrinkOptions.FinalSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.OptionType;
import kr.ktb.silko_be.menu.DrinkOptions.SweetnessAdjustment;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.session.FulfillmentType;

public final class OrderDtos {
    private OrderDtos() {}

    public record OrderOptionsRequest(@NotNull Temperature temperature, DrinkSize size,
                                      ExtraShot extraShot, SweetnessAdjustment sweetness) {
        public OrderOptionsRequest {
            if (size == null) size = DrinkSize.REGULAR;
            if (extraShot == null) extraShot = ExtraShot.NONE;
            if (sweetness == null) sweetness = SweetnessAdjustment.NORMAL;
        }
    }
    public record OrderItemRequest(@NotNull UUID menuId, @Min(1) @Max(20) int quantity,
                                   @Valid @NotNull OrderOptionsRequest options) {}
    public record OrderCreateRequest(
        @NotEmpty @Size(max = 20) List<@Valid OrderItemRequest> items
    ) {}
    public record OrderStatusRequest(@NotNull OrderStatus status) {}
    public record OrderOptionResponse(OptionType type, String code, String name, long additionalPrice) {}
    public record OrderItemResponse(String menuName, int quantity, long basePrice, long unitPrice, long subtotal,
                                    List<OrderOptionResponse> options, FinalSweetness finalSweetness) {}
    public record OrderResponse(UUID id, long orderNumber, OrderStatus status,
                                FulfillmentType fulfillmentType, PaymentMethod paymentMethod,
                                List<OrderItemResponse> items, long totalPrice,
                                OffsetDateTime createdAt, OffsetDateTime updatedAt) {}
    public record OrderStatusResponse(UUID id, long orderNumber, OrderStatus status,
                                      FulfillmentType fulfillmentType, boolean pickupReady,
                                      String message, OffsetDateTime updatedAt) {}
}
