#ifndef PS5_AGC_STAGE_METADATA_CONTRACT_H
#define PS5_AGC_STAGE_METADATA_CONTRACT_H

/* The runtime variant and generated shader metadata must be selected by the
 * same build decision.  A stale define must fail compilation, not survive as
 * a runtime size mismatch on the console. */
#if defined(STAGE_H_GEARS)
# if !defined(STAGE_H_GEARS_METADATA) || defined(STAGE_F_CUBE_METADATA)
#  error "Stage H/I requires Stage-H Gears metadata exclusively"
# endif
# include "../../probes/ps5-agc-phase0/stage_h_compiled_metadata.h"
#elif defined(STAGE_F_CUBE)
# if !defined(STAGE_F_CUBE_METADATA) || defined(STAGE_H_GEARS_METADATA)
#  error "Stage F/G requires Stage-F Cube metadata exclusively"
# endif
# include "../../probes/ps5-agc-phase0/stage_f_compiled_metadata.h"
#else
# if defined(STAGE_F_CUBE_METADATA) || defined(STAGE_H_GEARS_METADATA)
#  error "Stage E cannot consume Cube or Gears metadata"
# endif
# include "../../probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
#endif

#endif
