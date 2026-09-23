ALTER TABLE "GuestSession" ADD COLUMN "fulfillmentType" TEXT;
ALTER TABLE "Order" ADD COLUMN "fulfillmentType" TEXT NOT NULL DEFAULT 'dine_in';
