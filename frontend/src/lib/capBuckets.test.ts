import { describe, expect, it } from "vitest";
import { CAP_BUCKETS, capBucket } from "./capBuckets";

describe("capBucket", () => {
  it("has the six agreed buckets, biggest first", () => {
    expect(CAP_BUCKETS.map((b) => b.label)).toEqual(["Mega-cap", "Large-cap", "Mid-cap", "Small-cap", "Micro-cap", "Nano-cap"]);
  });
  it("puts a market value in its bucket, edges going to the bucket whose range ends there", () => {
    const id = (v: number) => capBucket(v)?.id;
    expect(id(2000000)).toBe("mega"); expect(id(200001)).toBe("mega"); expect(id(200000)).toBe("large"); expect(id(50001)).toBe("large"); expect(id(50000)).toBe("mid");
    expect(id(10001)).toBe("mid"); expect(id(10000)).toBe("small"); expect(id(2001)).toBe("small"); expect(id(2000)).toBe("micro"); expect(id(501)).toBe("micro");
    expect(id(500)).toBe("nano"); expect(id(0)).toBe("nano"); expect(id(12.5)).toBe("nano");
  });
  it("says nothing when the value is not known", () => {
    expect(capBucket(null)).toBeNull(); expect(capBucket(undefined)).toBeNull(); expect(capBucket(NaN)).toBeNull(); expect(capBucket(-5)).toBeNull();
  });
});
