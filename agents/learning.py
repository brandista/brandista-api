# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Learning System
TRUE SWARM EDITION - Continuous learning and adaptation

This enables agents to:
- Track prediction accuracy
- Learn from successes and failures
- Adapt behavior based on experience
- Improve over time
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    prediction_id: str
    agent_id: str
    prediction_type: str
    predicted_value: Any
    actual_value: Any = None
    confidence: float = 1.0
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    verified_at: Optional[datetime] = None
    was_correct: Optional[bool] = None
    error_margin: Optional[float] = None


@dataclass
class LearningStats:
    agent_id: str
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    avg_confidence: float = 0.0
    calibration_error: float = 0.0  # Difference between confidence and accuracy
    by_type: Dict[str, Dict[str, float]] = field(default_factory=dict)
    trend: str = "stable"  # improving, declining, stable


class LearningSystem:
    """Tracks and learns from agent predictions"""
    
    def __init__(self):
        self._predictions: Dict[str, Prediction] = {}
        self._verified: List[Prediction] = []
        self._agent_stats: Dict[str, LearningStats] = {}
        self._learned_rules: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._prediction_counter = 0
        
        logger.info("[LearningSystem] 🧠 Learning system initialized")
    
    def log_prediction(
        self,
        agent_id: str,
        prediction_type: str,
        predicted_value: Any,
        confidence: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a prediction for later verification"""
        self._prediction_counter += 1
        pred_id = f"pred_{agent_id}_{self._prediction_counter}"
        
        prediction = Prediction(
            prediction_id=pred_id,
            agent_id=agent_id,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            confidence=min(1.0, max(0.0, confidence)),
            context=context or {}
        )
        
        self._predictions[pred_id] = prediction
        
        # Initialize agent stats if needed
        if agent_id not in self._agent_stats:
            self._agent_stats[agent_id] = LearningStats(agent_id=agent_id)
        
        self._agent_stats[agent_id].total_predictions += 1
        
        logger.debug(f"[LearningSystem] 📝 Logged prediction {pred_id}: {prediction_type}")
        return pred_id
    
    def verify_prediction(self, prediction_id: str, actual_value: Any) -> Optional[bool]:
        """Verify a prediction with actual results"""
        prediction = self._predictions.get(prediction_id)
        if not prediction:
            return None
        
        prediction.actual_value = actual_value
        prediction.verified_at = datetime.now()
        
        # Determine correctness
        was_correct = self._evaluate_correctness(prediction)
        prediction.was_correct = was_correct
        
        # Update stats
        self._update_stats(prediction)
        
        # Move to verified
        self._verified.append(prediction)
        
        # Learn from result
        self._learn_from_prediction(prediction)
        
        logger.debug(
            f"[LearningSystem] ✓ Verified {prediction_id}: "
            f"{'correct' if was_correct else 'incorrect'}"
        )
        
        return was_correct
    
    def _evaluate_correctness(self, prediction: Prediction) -> bool:
        """Evaluate if prediction was correct"""
        predicted = prediction.predicted_value
        actual = prediction.actual_value
        
        # Numeric comparison with margin
        if isinstance(predicted, (int, float)) and isinstance(actual, (int, float)):
            margin = abs(predicted - actual)
            threshold = max(abs(predicted) * 0.2, 5)  # 20% or 5 points
            prediction.error_margin = margin
            return margin <= threshold
        
        # Boolean comparison
        if isinstance(predicted, bool) and isinstance(actual, bool):
            return predicted == actual
        
        # String comparison
        if isinstance(predicted, str) and isinstance(actual, str):
            return predicted.lower() == actual.lower()
        
        # List comparison (check overlap)
        if isinstance(predicted, list) and isinstance(actual, list):
            overlap = len(set(predicted) & set(actual))
            total = len(set(predicted) | set(actual))
            return overlap / total >= 0.5 if total > 0 else True
        
        # Default: exact match
        return predicted == actual
    
    def _update_stats(self, prediction: Prediction):
        """Update agent statistics"""
        stats = self._agent_stats.get(prediction.agent_id)
        if not stats:
            return
        
        if prediction.was_correct:
            stats.correct_predictions += 1
        
        # Update accuracy
        verified_count = len([p for p in self._verified if p.agent_id == prediction.agent_id])
        if verified_count > 0:
            stats.accuracy = stats.correct_predictions / verified_count
        
        # Update avg confidence
        confidences = [
            p.confidence for p in self._verified
            if p.agent_id == prediction.agent_id
        ]
        if confidences:
            stats.avg_confidence = statistics.mean(confidences)
        
        # Calculate calibration error
        stats.calibration_error = abs(stats.accuracy - stats.avg_confidence)
        
        # Update by-type stats
        ptype = prediction.prediction_type
        if ptype not in stats.by_type:
            stats.by_type[ptype] = {'total': 0, 'correct': 0, 'accuracy': 0.0}
        
        stats.by_type[ptype]['total'] += 1
        if prediction.was_correct:
            stats.by_type[ptype]['correct'] += 1
        
        total = stats.by_type[ptype]['total']
        correct = stats.by_type[ptype]['correct']
        stats.by_type[ptype]['accuracy'] = correct / total if total > 0 else 0.0
        
        # Determine trend
        recent = [p for p in self._verified[-20:] if p.agent_id == prediction.agent_id]
        if len(recent) >= 10:
            first_half = recent[:len(recent)//2]
            second_half = recent[len(recent)//2:]
            
            first_acc = sum(1 for p in first_half if p.was_correct) / len(first_half)
            second_acc = sum(1 for p in second_half if p.was_correct) / len(second_half)
            
            if second_acc > first_acc + 0.1:
                stats.trend = "improving"
            elif second_acc < first_acc - 0.1:
                stats.trend = "declining"
            else:
                stats.trend = "stable"
    
    def _learn_from_prediction(self, prediction: Prediction):
        """Extract learnings from prediction results"""
        agent_id = prediction.agent_id
        
        # Build rule from context
        if prediction.context and not prediction.was_correct:
            rule = {
                'type': 'avoid',
                'prediction_type': prediction.prediction_type,
                'context_pattern': prediction.context,
                'reason': f"Predicted {prediction.predicted_value}, actual was {prediction.actual_value}",
                'created_at': datetime.now().isoformat()
            }
            self._learned_rules[agent_id].append(rule)
            
            # Keep only recent rules
            self._learned_rules[agent_id] = self._learned_rules[agent_id][-50:]
    
    def should_adjust_confidence(
        self,
        agent_id: str,
        prediction_type: str
    ) -> Tuple[bool, float]:
        """Check if agent should adjust confidence based on history"""
        stats = self._agent_stats.get(agent_id)
        if not stats:
            return False, 1.0
        
        # Check type-specific stats
        type_stats = stats.by_type.get(prediction_type)
        if type_stats and type_stats['total'] >= 5:
            accuracy = type_stats['accuracy']
            
            if accuracy < 0.5:
                return True, 0.7  # Reduce confidence
            elif accuracy > 0.9:
                return True, 1.1  # Can increase confidence slightly
        
        # Check overall calibration
        if stats.calibration_error > 0.2 and stats.total_predictions >= 10:
            if stats.avg_confidence > stats.accuracy:
                return True, 0.85  # Over-confident, reduce
        
        return False, 1.0
    
    def get_agent_stats(self, agent_id: str) -> Optional[LearningStats]:
        """Get learning stats for agent"""
        return self._agent_stats.get(agent_id)
    
    def get_learned_rules(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get learned rules for agent"""
        return self._learned_rules.get(agent_id, [])
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get all statistics"""
        return {
            'total_predictions': sum(s.total_predictions for s in self._agent_stats.values()),
            'total_verified': len(self._verified),
            'agents': {
                agent_id: {
                    'total': stats.total_predictions,
                    'correct': stats.correct_predictions,
                    'accuracy': round(stats.accuracy, 3),
                    'calibration_error': round(stats.calibration_error, 3),
                    'trend': stats.trend
                }
                for agent_id, stats in self._agent_stats.items()
            }
        }
    
    def reset(self):
        """Full reset"""
        self._predictions.clear()
        self._verified.clear()
        self._agent_stats.clear()
        self._learned_rules.clear()
        self._prediction_counter = 0


_learning_system: Optional[LearningSystem] = None

def get_learning_system() -> LearningSystem:
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem()
    return _learning_system

def reset_learning_system():
    global _learning_system
    if _learning_system:
        _learning_system.reset()
    _learning_system = None
