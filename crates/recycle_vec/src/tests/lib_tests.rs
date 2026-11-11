// SPDX-License-Identifier: GPL-3.0-or-later

use super::*;

// -- Buffer take / restore -----------------------------------------------

#[test]
fn buffer_take_hands_out_the_items_and_leaves_an_empty_pool() {
    let mut queue: RecycleVec<u32> = RecycleVec::new();
    queue.push(1);
    queue.push(2);

    let taken = queue.buffer_take();
    assert!(queue.is_empty());
    assert_eq!(&taken[..], &[1, 2][..]);

    queue.buffer_restore(taken);
}

#[test]
fn buffer_restore_puts_the_leftover_before_what_was_queued() {
    let mut queue: RecycleVec<u32> = RecycleVec::new();
    queue.push(1);

    // A drain loop that stops early leaves items in the taken buffer, while
    // the loop body pushes into the pool it left behind.
    let taken = queue.buffer_take();
    queue.push(2);
    queue.buffer_restore(taken);

    assert_eq!(&queue[..], &[1, 2][..]);
}

#[test]
fn buffer_restore_carries_what_was_queued_during_the_drain() {
    let mut queue: RecycleVec<u32> = RecycleVec::new();
    queue.push(1);

    let mut taken = queue.buffer_take();
    let drained: Vec<u32> = taken.drain(..).collect();
    assert_eq!(drained, vec![1]);
    queue.push(2);
    queue.buffer_restore(taken);

    assert_eq!(&queue[..], &[2][..]);
}

#[test]
fn buffer_restore_ends_the_cycle() {
    let mut queue: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = queue.capacity();

    // One item per cycle, well under half the allocation.
    for _ in 0..SHRINK_UNDERUSE_CYCLES {
        queue.push(1);
        let mut taken = queue.buffer_take();
        taken.drain(..).for_each(drop);
        queue.buffer_restore(taken);
    }

    assert_eq!(queue.capacity(), cap / SHRINK_UNDERUSE_RATIO);
}

#[test]
fn buffer_take_keeps_the_allocation_across_a_cycle() {
    let mut queue: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = queue.capacity();

    queue.push(1);
    let mut taken = queue.buffer_take();
    taken.drain(..).for_each(drop);
    queue.buffer_restore(taken);

    assert_eq!(queue.capacity(), cap);
}

#[test]
fn buffer_restore_measures_a_buffer_no_drain_recorded() {
    // Only `drain` and the restore record, so a caller that consumed the
    // items some other way leaves the restore as the sole measurement. A
    // buffer holding more than half its allocation must not read as idle.
    let mut queue: RecycleVec<u32> = RecycleVec::with_capacity(16);
    for i in 0..9 {
        queue.push(i);
    }
    let cap = queue.capacity();

    for _ in 0..SHRINK_UNDERUSE_CYCLES {
        let taken = queue.buffer_take();
        queue.buffer_restore(taken);
    }

    assert_eq!(queue.capacity(), cap);
}

#[test]
fn lend_restore_keeps_the_allocation() {
    // What the lend exists for: a missed put-back is neither a compile error
    // nor a panic, only a silent reallocation on the next borrow.
    let mut pool: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = pool.capacity();

    let mut lent = pool.buffer_take();
    lent.push(1);
    lent.drain(..);
    pool.lend_restore(lent);

    assert_eq!(pool.capacity(), cap, "the lend gave the allocation back");
}

// -- Shrink heuristic ----------------------------------------------------

#[test]
fn clear_shrinks_after_sustained_underuse() {
    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = buf.capacity();

    for _ in 0..(SHRINK_UNDERUSE_CYCLES - 1) {
        buf.push(1);
        buf.clear();
    }
    assert_eq!(buf.capacity(), cap);

    buf.push(1);
    buf.clear();
    assert_eq!(buf.capacity(), cap / SHRINK_UNDERUSE_RATIO);
}

#[test]
fn a_well_used_cycle_resets_the_counter() {
    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = buf.capacity();
    let over_half = cap / SHRINK_UNDERUSE_RATIO + 1;

    for _ in 0..(SHRINK_UNDERUSE_CYCLES - 1) {
        buf.push(1);
        buf.clear();
    }
    for _ in 0..over_half {
        buf.push(1);
    }
    buf.clear();

    // The counter restarted, so another near-threshold run still does not
    // reach it.
    for _ in 0..(SHRINK_UNDERUSE_CYCLES - 1) {
        buf.push(1);
        buf.clear();
    }
    assert_eq!(buf.capacity(), cap);
}

#[test]
fn shrink_fires_at_most_once_per_threshold_of_cycles() {
    // The bound that makes the heuristic safe to apply widely: a workload
    // that shrinks and regrows pays one reallocation per threshold, not one
    // per cycle. Asserting the final capacity would miss a break here - the
    // same capacities are reached either way, only sooner.
    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let capacity_initial = buf.capacity();
    let halvings = capacity_initial.ilog2();

    let mut capacity = capacity_initial;
    let mut fired = Vec::new();
    for cycle in 0..(SHRINK_UNDERUSE_CYCLES * (halvings + 1)) {
        buf.push(1);
        buf.clear();
        if buf.capacity() != capacity {
            fired.push(cycle);
            capacity = buf.capacity();
        }
    }

    let expected: Vec<u32> = (1..=halvings)
        .map(|n| n * SHRINK_UNDERUSE_CYCLES - 1)
        .collect();
    assert_eq!(fired, expected, "one shrink per threshold of cycles");
    assert_eq!(capacity, 1, "converged onto the peak and stopped");
}

#[test]
fn a_busy_cycle_does_not_hold_its_peak_into_later_ones() {
    // The peak belongs to the cycle that saw it. Carried forward, one busy
    // cycle would read as busy for ever and the buffer would never shrink.
    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = buf.capacity();

    for _ in 0..cap {
        buf.push(1);
    }
    buf.clear();

    for _ in 0..SHRINK_UNDERUSE_CYCLES {
        buf.push(1);
        buf.clear();
    }

    assert_eq!(
        buf.capacity(),
        cap / SHRINK_UNDERUSE_RATIO,
        "the busy cycle's peak did not outlive it"
    );
}

#[test]
fn an_unallocated_buffer_does_not_bank_underuse_cycles() {
    // A buffer that has never allocated is unused, not underused. Counting
    // those cycles would prime the counter, so the first allocation it does
    // make could be given back a single cycle later.
    let mut buf: RecycleVec<u32> = RecycleVec::new();
    for _ in 0..(SHRINK_UNDERUSE_CYCLES - 1) {
        buf.clear();
    }

    buf.push(1);
    let grown = buf.capacity();
    buf.clear();

    assert_eq!(buf.capacity(), grown, "the idle cycles banked nothing");
}
#[test]
fn lends_within_a_cycle_cost_no_boundaries_of_their_own() {
    // A buffer cleared once per pass may be lent as scratch any number of
    // times within it. A lend drains rather than clears, so the pass's clear
    // stays the only boundary - were it a clear, a pass would spend a cycle
    // per lend and reach the threshold in a fraction of them.
    for lends in [0u32, 1, 4] {
        let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(64);
        let mut passes: u32 = 0;
        while buf.capacity() == 64 {
            buf.clear();
            for _ in 0..lends {
                for i in 0..4 {
                    buf.push(i);
                }
                buf.drain(..);
            }
            passes += 1;
            assert!(passes <= SHRINK_UNDERUSE_CYCLES, "shrank early on {lends}");
        }
        assert_eq!(passes, SHRINK_UNDERUSE_CYCLES, "one cycle a pass");
    }
}

#[test]
fn drain_snapshots_the_peak_for_a_later_clear() {
    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = buf.capacity();
    let over_half = cap / SHRINK_UNDERUSE_RATIO + 1;

    // A buffer drained to release its contents early, then cleared at the
    // start of the next pass. The clear must see the peak, not the emptied
    // length.
    for _ in 0..SHRINK_UNDERUSE_CYCLES {
        for _ in 0..over_half {
            buf.push(1);
        }
        buf.drain(..).for_each(drop);
        buf.clear();
    }

    assert_eq!(buf.capacity(), cap);
}

#[test]
fn shrink_check_measures_the_live_length() {
    let mut pool: RecycleVec<u32> = RecycleVec::with_capacity(64);
    let cap = pool.capacity();

    // A pool that is never cleared, holding one item across every check.
    pool.push(1);
    for _ in 0..SHRINK_UNDERUSE_CYCLES {
        pool.shrink_check();
    }

    assert_eq!(pool.capacity(), cap / SHRINK_UNDERUSE_RATIO);
}

// -- Shrink policy -------------------------------------------------------

#[test]
fn shrink_policy_target_never_drops_below_the_peak() {
    let mut policy: ShrinkPolicy = ShrinkPolicy::new();
    let capacity = 64;
    // The largest peak that still counts as underuse.
    let peak = capacity / SHRINK_UNDERUSE_RATIO;

    let mut target = None;
    for _ in 0..SHRINK_UNDERUSE_CYCLES {
        policy.record(peak);
        target = policy.cycle_end(capacity);
    }

    assert_eq!(target, Some(peak));
}

#[test]
fn shrink_policy_counts_only_consecutive_cycles() {
    let mut policy: ShrinkPolicy = ShrinkPolicy::new();
    for _ in 0..(SHRINK_UNDERUSE_CYCLES - 1) {
        policy.record(1);
        assert_eq!(policy.cycle_end(64), None);
    }

    // A cycle above the threshold restarts the count.
    policy.record(64);
    assert_eq!(policy.cycle_end(64), None);

    for _ in 0..(SHRINK_UNDERUSE_CYCLES - 1) {
        policy.record(1);
        assert_eq!(policy.cycle_end(64), None);
    }
}

#[test]
fn debug_reads_as_the_sequence_it_wraps() {
    // The shrink bookkeeping is not part of the value: a `{:?}` dump prints
    // what a plain `Vec` field would.
    let mut buf: RecycleVec<u32> = RecycleVec::new();
    buf.push(1);
    buf.push(2);

    assert_eq!(format!("{buf:?}"), format!("{:?}", vec![1u32, 2]));
}

#[test]
#[should_panic(expected = "nothing may reach a lent buffer")]
fn lend_restore_catches_a_push_the_assignment_would_drop() {
    let mut pool: RecycleVec<u32> = RecycleVec::new();
    pool.push(1);
    let lent = pool.buffer_take();

    // A caller that pushes into the pool while it is lent: the restore
    // overwrites the field, so without the assert this vanishes.
    pool.push(2);
    pool.lend_restore(lent);
}

#[test]
fn clearing_an_empty_buffer_still_spends_a_cycle() {
    // Why a caller lending a buffer out should assert it is empty on entry
    // rather than clear it: the clear is a cycle boundary whether or not it moves
    // anything, so a redundant one halves the threshold for that buffer.
    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(16);
    let cap = buf.capacity();
    for _ in 0..(SHRINK_UNDERUSE_CYCLES / 2) {
        buf.clear();
        for i in 0..4 {
            buf.push(i);
        }
        buf.clear();
    }
    assert_eq!(
        buf.capacity(),
        cap / SHRINK_UNDERUSE_RATIO,
        "two boundaries per pass reached it early"
    );

    let mut buf: RecycleVec<u32> = RecycleVec::with_capacity(16);
    for _ in 0..(SHRINK_UNDERUSE_CYCLES / 2) {
        for i in 0..4 {
            buf.push(i);
        }
        buf.clear();
    }
    assert_eq!(buf.capacity(), cap, "one boundary per pass is only halfway");
}

#[test]
#[should_panic(expected = "buffer is already lent")]
fn taking_a_lent_buffer_again_is_caught() {
    let mut pool: RecycleVec<u32> = RecycleVec::with_capacity(16);
    let outer = pool.buffer_take();

    // The nested take finds the emptied pool and would hand out a fresh
    // allocation, which the outer restore then overwrites.
    let inner = pool.buffer_take();
    drop((outer, inner));
}

#[test]
#[should_panic(expected = "restoring a buffer that was never taken")]
fn restoring_a_buffer_that_was_never_taken_is_caught() {
    let mut pool: RecycleVec<u32> = RecycleVec::new();
    pool.lend_restore(RecycleVec::new());
}

#[test]
fn parameters_set_the_target_and_the_threshold() {
    let mut buf: RecycleVec<u32, 4, 3> = RecycleVec::with_capacity(64);
    let cap = buf.capacity();

    for _ in 0..2 {
        buf.push(1);
        buf.clear();
    }
    assert_eq!(buf.capacity(), cap);

    buf.push(1);
    buf.clear();
    assert_eq!(buf.capacity(), cap / 4);
}
