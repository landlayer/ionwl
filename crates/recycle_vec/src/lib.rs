// SPDX-License-Identifier: GPL-3.0-or-later

//! A `Vec` that gives back its allocation once a workload stops needing it.

/// Default `UNDERUSE_RATIO`: a cycle is underused when its peak is at most
/// `capacity / UNDERUSE_RATIO`.
pub const SHRINK_UNDERUSE_RATIO: usize = 2;
/// Default `UNDERUSE_CYCLES`: consecutive underutilized cycles before shrinking.
pub const SHRINK_UNDERUSE_CYCLES: u32 = 32;

/// Consecutive-underuse counter behind [`RecycleVec`], for a collection that
/// measures its own usage.
///
/// A cycle records the usage it saw and then ends. Once `UNDERUSE_CYCLES`
/// consecutive cycles have used at most `capacity / UNDERUSE_RATIO`, the
/// owner is told to shrink to that size; any cycle above it resets the count.
/// The ratio is written as its integer denominator, so 2 means one half: a
/// cycle is underused when it would have fit after the shrink.
///
/// Self-limiting: capacity converges into `[peak, UNDERUSE_RATIO * peak)` and
/// stops, so a steady workload shrinks a few times and then never fires
/// again, and one that falls idle is released entirely. Even a workload
/// alternating enough to shrink and regrow every window measures no slower
/// than never shrinking: the smaller working set pays for the reallocation,
/// which is bounded at one per `UNDERUSE_CYCLES` cycles.
///
/// The owner decides what "capacity" and "shrink" mean - spare allocation,
/// pooled entries, queued bytes - so the policy holds no collection of its
/// own.
///
/// `UNDERUSE_RATIO` must be at least 2 - 1 would never shrink and 0 divides
/// by zero - and `UNDERUSE_CYCLES` at least 1; other values fail to compile.
/// Defaults do not drive inference, so a `new()` whose type nothing else pins
/// needs it written out.
pub struct ShrinkPolicy<
    const UNDERUSE_RATIO: usize = SHRINK_UNDERUSE_RATIO,
    const UNDERUSE_CYCLES: u32 = SHRINK_UNDERUSE_CYCLES,
> {
    peak: usize,
    underuse_count: u32,
}

// Marked `#[inline]` as callers reach these across a crate boundary, without LTO.
impl<const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32>
    ShrinkPolicy<UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    #[inline]
    #[must_use]
    pub const fn new() -> Self {
        const {
            assert!(UNDERUSE_RATIO >= 2, "`UNDERUSE_RATIO` must be at least 2");
            assert!(UNDERUSE_CYCLES >= 1, "`UNDERUSE_CYCLES` must be at least 1");
        }
        Self {
            peak: 0,
            underuse_count: 0,
        }
    }

    /// Record usage seen within the current cycle.
    #[inline]
    pub fn record(&mut self, used: usize) {
        self.peak = self.peak.max(used);
    }

    /// End the cycle, returning the size to shrink to once the threshold is
    /// reached.
    #[inline]
    pub fn cycle_end(&mut self, capacity: usize) -> Option<usize> {
        let peak = self.peak;
        self.peak = 0;
        let target = capacity / UNDERUSE_RATIO;
        if capacity == 0 || peak > target {
            self.underuse_count = 0;
            return None;
        }
        self.underuse_count += 1;
        if self.underuse_count < UNDERUSE_CYCLES {
            return None;
        }
        self.underuse_count = 0;
        Some(target)
    }
}

impl<const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> Default
    for ShrinkPolicy<UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    fn default() -> Self {
        Self::new()
    }
}

/// A Vec that tracks peak usage and periodically shrinks when underutilized.
///
/// Used for buffers that must be collected (not lazy iterators) because their
/// consumers require contiguous slices, iterate them multiple times or in
/// reverse, or receive elements from multiple independent producers. Also
/// used as object pools (`RecycleVec<Vec<T>>`) where items are popped for
/// reuse and pushed back once done with.
///
/// A cycle ends at [`clear`](RecycleVec::clear), or for a queue handed out
/// through [`buffer_take`](RecycleVec::buffer_take) at the matching
/// [`buffer_restore`](RecycleVec::buffer_restore); both measure the peak
/// length reached during it. Pools whose items persist between uses never
/// end one, so they call [`shrink_check`](RecycleVec::shrink_check) against the
/// live length instead.
///
/// If the measured usage was at most `capacity / UNDERUSE_RATIO`, an internal
/// counter increments; once `UNDERUSE_CYCLES` consecutive cycles are
/// underutilized the allocation shrinks to that size. Any cycle that exceeds
/// it resets the counter to zero. Both parameters are passed on to
/// [`ShrinkPolicy`].
///
/// The counter is shared, so a buffer driven by more than one of these - a
/// scratch that clears per use and is checked once per pass as well - reaches
/// the threshold sooner, not differently.
///
/// Usage is recorded by [`clear`](RecycleVec::clear),
/// [`drain`](RecycleVec::drain) and
/// [`shrink_check`](RecycleVec::shrink_check); `push` and `pop` do not. A
/// buffer that fills by `push` and empties by `pop` therefore reaches `clear`
/// already empty, reads as idle however full it got, and shrinks under a load
/// that needed every slot - so such a buffer wants a `ShrinkPolicy` it records
/// into itself, not this type.
pub struct RecycleVec<
    T,
    const UNDERUSE_RATIO: usize = SHRINK_UNDERUSE_RATIO,
    const UNDERUSE_CYCLES: u32 = SHRINK_UNDERUSE_CYCLES,
> {
    inner: Vec<T>,
    shrink: ShrinkPolicy<UNDERUSE_RATIO, UNDERUSE_CYCLES>,
    /// Whether the buffer is out on loan. Lives on the emptied pool a take
    /// leaves behind, so a nested take can see it; a restore clears it by
    /// overwriting the pool.
    ///
    /// The `lent_*` helpers wrap `assert!` in `#[cfg(debug_assertions)]`
    /// rather than use `debug_assert!`, whose condition still type-checks in
    /// release, where this field is absent. Tests build with
    /// `debug_assertions`, so only a release build catches that.
    #[cfg(debug_assertions)]
    lent: bool,
}

impl<T, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32>
    RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    #[must_use]
    pub const fn new() -> Self {
        Self {
            inner: Vec::new(),
            shrink: ShrinkPolicy::new(),
            #[cfg(debug_assertions)]
            lent: false,
        }
    }

    #[must_use]
    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            inner: Vec::with_capacity(capacity),
            ..Self::new()
        }
    }

    pub fn push(&mut self, value: T) {
        self.inner.push(value);
    }

    pub fn extend<I: IntoIterator<Item = T>>(&mut self, iter: I) {
        self.inner.extend(iter);
    }

    /// Drain elements, snapshotting peak length before the drain empties the vec.
    ///
    /// Ends no cycle: for a buffer whose boundary lies elsewhere. `record`
    /// keeps the peak as a max, so that boundary still sees what this drain
    /// measured.
    pub fn drain<R: std::ops::RangeBounds<usize>>(&mut self, range: R) -> std::vec::Drain<'_, T> {
        self.shrink.record(self.inner.len());
        self.inner.drain(range)
    }

    /// End the current cycle: check utilization, maybe shrink, then clear.
    ///
    /// A boundary even with nothing to empty, so a buffer whose cycle ends
    /// elsewhere wants [`drain`](RecycleVec::drain) instead - two boundaries a
    /// cycle halve the passes to the shrink threshold. Converting a `Vec` to
    /// this type promotes its every `clear` into one.
    pub fn clear(&mut self) {
        self.shrink.record(self.inner.len());
        // Emptied before the cycle ends: a shrink on a full buffer would
        // reallocate and copy every element, only to drop them here.
        self.inner.clear();
        self.cycle_end();
    }

    pub fn pop(&mut self) -> Option<T> {
        self.inner.pop()
    }

    pub fn dedup(&mut self)
    where
        T: PartialEq,
    {
        self.inner.dedup();
    }

    /// Move every element of `other` onto the end of this buffer, leaving
    /// `other` empty.
    pub fn append(&mut self, other: &mut Self) {
        self.inner.append(&mut other.inner);
    }

    /// Take the buffer out whole, leaving an empty pool behind.
    ///
    /// For a queue whose drain loop needs `&mut` access to the queue's owner:
    /// take it, drain the taken value, then return it through
    /// [`buffer_restore`](RecycleVec::buffer_restore), which ends the cycle.
    /// A caller that only lends the buffer out returns it through
    /// [`lend_restore`](RecycleVec::lend_restore) instead.
    ///
    /// The shrink counters describe the allocation, so they ride along and
    /// come back with it. The lent mark describes the pool, so it stays.
    #[must_use = "the take hands over the allocation; give it back with buffer_restore or lend_restore"]
    pub fn buffer_take(&mut self) -> Self {
        self.lent_free_assert();
        std::mem::replace(self, Self::lent_placeholder())
    }

    /// Put a lent buffer back, for the shape where nothing should reach the
    /// pool while it is out.
    ///
    /// Where [`buffer_restore`](RecycleVec::buffer_restore) carries what a
    /// drain loop queued, a push here is a caller bug the assignment would
    /// drop silently - hence the assert. Nor does this end a cycle: a lend is
    /// not a unit of work, and the caller has a boundary of its own.
    pub fn lend_restore(&mut self, buffer: Self) {
        self.lent_assert();
        debug_assert!(
            self.is_empty(),
            "nothing may reach a lent buffer - the restore would drop it"
        );
        *self = buffer;
    }

    /// Put a taken buffer back, keeping its allocation and carrying whatever
    /// was pushed into the pool while it was out. Order holds: what the buffer
    /// still carries comes before what was queued while it was gone.
    ///
    /// This ends the cycle, against the peak the taken buffer recorded across
    /// its drains - the whole cycle's, re-drained cascades included, which is
    /// what the queue had to hold. What it still holds here is recorded too,
    /// the way [`clear`](RecycleVec::clear) measures before emptying, so a
    /// caller that consumed the buffer without draining is measured rather
    /// than read as idle.
    pub fn buffer_restore(&mut self, mut buffer: Self) {
        self.lent_assert();
        buffer.append(self);
        *self = buffer;
        self.shrink.record(self.inner.len());
        self.cycle_end();
    }

    /// Fail if the buffer is already lent out.
    #[inline]
    fn lent_free_assert(&self) {
        #[cfg(debug_assertions)]
        assert!(
            !self.lent,
            "buffer is already lent - the inner take would hand out a fresh \
             allocation, dropped again when the outer restore overwrites it"
        );
    }

    /// Fail if the buffer being restored was never taken.
    #[inline]
    fn lent_assert(&self) {
        #[cfg(debug_assertions)]
        assert!(self.lent, "restoring a buffer that was never taken");
    }

    /// The empty pool a take leaves in place of the buffer it hands out.
    #[inline]
    fn lent_placeholder() -> Self {
        Self {
            #[cfg(debug_assertions)]
            lent: true,
            ..Self::new()
        }
    }

    /// Current allocation.
    #[must_use]
    pub fn capacity(&self) -> usize {
        self.inner.capacity()
    }

    /// Check utilization and maybe shrink, without clearing contents.
    ///
    /// Use this for pool-style Vecs where items persist between uses.
    pub fn shrink_check(&mut self) {
        self.shrink.record(self.inner.len());
        self.cycle_end();
    }

    /// Apply the policy's verdict for a cycle that just ended.
    fn cycle_end(&mut self) {
        if let Some(capacity) = self.shrink.cycle_end(self.inner.capacity()) {
            self.inner.shrink_to(capacity);
        }
    }
}

impl<T, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> std::ops::Deref
    for RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    type Target = [T];
    fn deref(&self) -> &[T] {
        &self.inner
    }
}

impl<T, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> std::ops::DerefMut
    for RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    fn deref_mut(&mut self) -> &mut [T] {
        &mut self.inner
    }
}

impl<'a, T, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> IntoIterator
    for &'a RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.inner.iter()
    }
}

impl<'a, T, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> IntoIterator
    for &'a mut RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    type Item = &'a mut T;
    type IntoIter = std::slice::IterMut<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.inner.iter_mut()
    }
}

/// Prints as the sequence it wraps: the shrink bookkeeping is not part of the
/// buffer's value, so a `{:?}` dump of an owning struct reads as it would for
/// a plain `Vec` field.
impl<T: std::fmt::Debug, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> std::fmt::Debug
    for RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.inner.fmt(f)
    }
}

impl<T, const UNDERUSE_RATIO: usize, const UNDERUSE_CYCLES: u32> Default
    for RecycleVec<T, UNDERUSE_RATIO, UNDERUSE_CYCLES>
{
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
#[path = "tests/lib_tests.rs"]
mod tests;
