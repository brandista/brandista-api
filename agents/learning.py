# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Learning & Adaptation System
TRUE SWARM AGENTS - Agents learn from experience

This enables agents to:
- Track prediction accuracy
- Learn from mistakes
- Adapt strategies over time
- Improve recommendations
- Build expertise through experience

Think of this as the agents' "memory of what works and what doesn't".
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    """
    A prediction made by an agent.
    
    Agents make predictions about:
    - Score changes
    - Threat levels
    - Opportunity impact
    - Action effectiveness
    
    We track these to measure accuracy.
    """
    prediction_id: str
    agent_id: str
    prediction_type: str  # 'score_change', 'threat_level', 'opportunity_impact', etc.
    predicted_value: Any
    actual_value: Optional[Any] = None
    confidence: float = 1.0
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    verified_at: Optional[datetime] = None
    accuracy_score: Optional[float] = None  # 0-1, how accurate was prediction
    
    def is_verified(self) -> bool:
        """Check if prediction has been verified"""
        return self.actual_value is not None
    
    def calculate_accuracy(self) -> float:
        """
        Calculate prediction accuracy.
        
        Returns:
            Score from 0 (totally wrong) to 1 (perfect)
        """
        if not self.is_verified():
            return 0.0
        
        # Different calculation based on type
        if self.prediction_type == 'score_change':
            # Compare predicted vs actual score change
            pred = float(self.predicted_value)
            actual = float(self.actual_value)
            
            # Perfect if within ±2 points
            error = abs(pred - actual)
            if error <= 2:
                accuracy = 1.0
            elif error <= 5:
                accuracy = 0.8
            elif error <= 10:
                accuracy = 0.5
            else:
                accuracy = 0.2
            
            return accuracy
        
        elif self.prediction_type == 'threat_level':
            # Categorical - exact match or close
            pred = str(self.predicted_value).lower()
            actual = str(self.actual_value).lower()
            
            if pred == actual:
                return 1.0
            
            # Partial credit for being one level off
            levels = ['low', 'medium', 'high', 'critical']
            try:
                pred_idx = levels.index(pred)
                actual_idx = levels.index(actual)
                diff = abs(pred_idx - actual_idx)
                
                if diff == 1:
                    return 0.7
                elif diff == 2:
                    return 0.4
                else:
                    return 0.1
            except ValueError:
                return 0.0
        
        else:
            # Generic - exact match
            return 1.0 if self.predicted_value == self.actual_value else 0.0


@dataclass
class LearningStats:
    """Statistics for an agent's learning"""
    agent_id: str
    total_predictions: int = 0
    verified_predictions: int = 0
    average_accuracy: float = 0.0
    accuracy_by_type: Dict[str, float] = field(default_factory=dict)
    confidence_calibration: float = 0.0  # How well confidence matches accuracy
    recent_trend: str = "stable"  # improving, stable, declining
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'total_predictions': self.total_predictions,
            'verified_predictions': self.verified_predictions,
            'average_accuracy': round(self.average_accuracy, 3),
            'accuracy_by_type': {
                k: round(v, 3) for k, v in self.accuracy_by_type.items()
            },
            'confidence_calibration': round(self.confidence_calibration, 3),
            'recent_trend': self.recent_trend,
            'last_updated': self.last_updated.isoformat()
        }


class LearningSystem:
    """
    Learning and adaptation system for agents.
    
    Tracks predictions, calculates accuracy, adapts behavior.
    """
    
    def __init__(self):
        # All predictions: prediction_id -> Prediction
        self.predictions: Dict[str, Prediction] = {}
        
        # Predictions by agent: agent_id -> [prediction_ids]
        self.predictions_by_agent: Dict[str, List[str]] = defaultdict(list)
        
        # Statistics per agent
        self.stats_by_agent: Dict[str, LearningStats] = {}
        
        # Adaptation rules learned
        self.learned_rules: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        logger.info("[LearningSystem] 🧠 Learning system initialized")
    
    def log_prediction(
        self,
        agent_id: str,
        prediction_type: str,
        predicted_value: Any,
        confidence: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a prediction made by an agent.
        
        Args:
            agent_id: Agent making prediction
            prediction_type: Type of prediction
            predicted_value: What agent predicts
            confidence: Agent's confidence (0-1)
            context: Additional context
            
        Returns:
            prediction_id for later verification
        
        Example:
            prediction_id = learning.log_prediction(
                agent_id='strategist',
                prediction_type='score_change',
                predicted_value=+7,  # Predicts score will increase by 7
                confidence=0.85
            )
            
            # Later, when actual results known...
            learning.verify_prediction(
                prediction_id,
                actual_value=+5  # Actually increased by 5
            )
        """
        prediction_id = f"{agent_id}_{prediction_type}_{int(datetime.now().timestamp() * 1000)}"
        
        prediction = Prediction(
            prediction_id=prediction_id,
            agent_id=agent_id,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            confidence=confidence,
            context=context or {}
        )
        
        # Store prediction
        self.predictions[prediction_id] = prediction
        self.predictions_by_agent[agent_id].append(prediction_id)
        
        # Update stats
        if agent_id not in self.stats_by_agent:
            self.stats_by_agent[agent_id] = LearningStats(agent_id=agent_id)
        
        self.stats_by_agent[agent_id].total_predictions += 1
        
        logger.info(
            f"[LearningSystem] 📝 {agent_id} predicted {prediction_type}: "
            f"{predicted_value} (confidence: {confidence:.2f})"
        )
        
        return prediction_id
    
    def verify_prediction(
        self,
        prediction_id: str,
        actual_value: Any
    ):
        """
        Verify a prediction with actual results.
        
        Args:
            prediction_id: ID from log_prediction
            actual_value: What actually happened
        """
        prediction = self.predictions.get(prediction_id)
        if not prediction:
            logger.warning(
                f"[LearningSystem] ⚠️ Unknown prediction: {prediction_id}"
            )
            return
        
        # Update prediction
        prediction.actual_value = actual_value
        prediction.verified_at = datetime.now()
        prediction.accuracy_score = prediction.calculate_accuracy()
        
        # Update stats
        agent_id = prediction.agent_id
        stats = self.stats_by_agent[agent_id]
        stats.verified_predictions += 1
        
        # Recalculate average accuracy
        verified = [
            self.predictions[pid]
            for pid in self.predictions_by_agent[agent_id]
            if self.predictions[pid].is_verified()
        ]
        
        if verified:
            stats.average_accuracy = statistics.mean(
                p.accuracy_score for p in verified if p.accuracy_score is not None
            )
            
            # Accuracy by type
            by_type = defaultdict(list)
            for p in verified:
                if p.accuracy_score is not None:
                    by_type[p.prediction_type].append(p.accuracy_score)
            
            stats.accuracy_by_type = {
                ptype: statistics.mean(scores)
                for ptype, scores in by_type.items()
            }
            
            # Confidence calibration
            # Good calibration = confidence matches accuracy
            calibration_errors = [
                abs(p.confidence - (p.accuracy_score or 0))
                for p in verified
                if p.accuracy_score is not None
            ]
            if calibration_errors:
                avg_error = statistics.mean(calibration_errors)
                stats.confidence_calibration = 1.0 - avg_error
            
            # Recent trend (last 5 predictions)
            recent = verified[-5:]
            if len(recent) >= 3:
                recent_accuracy = [p.accuracy_score for p in recent if p.accuracy_score]
                if len(recent_accuracy) >= 3:
                    if recent_accuracy[-1] > recent_accuracy[0]:
                        stats.recent_trend = "improving"
                    elif recent_accuracy[-1] < recent_accuracy[0]:
                        stats.recent_trend = "declining"
                    else:
                        stats.recent_trend = "stable"
        
        stats.last_updated = datetime.now()
        
        logger.info(
            f"[LearningSystem] ✅ Verified {agent_id} prediction: "
            f"predicted={prediction.predicted_value}, "
            f"actual={actual_value}, "
            f"accuracy={prediction.accuracy_score:.2f}"
        )
        
        # Learn from this prediction
        self._learn_from_prediction(prediction)
    
    def _learn_from_prediction(self, prediction: Prediction):
        """
        Learn adaptation rules from prediction results.
        
        This is where the magic happens - agents learn what works.
        """
        agent_id = prediction.agent_id
        accuracy = prediction.accuracy_score
        
        if accuracy is None or accuracy < 0.3:
            # Bad prediction - learn what NOT to do
            rule = {
                'type': 'avoid',
                'prediction_type': prediction.prediction_type,
                'context': prediction.context,
                'reason': f'Low accuracy ({accuracy:.2f})',
                'learned_at': datetime.now().isoformat()
            }
            self.learned_rules[agent_id].append(rule)
            
            logger.info(
                f"[LearningSystem] 📚 {agent_id} learned to avoid: "
                f"{prediction.prediction_type} in context {prediction.context}"
            )
        
        elif accuracy > 0.8:
            # Good prediction - learn what TO do
            rule = {
                'type': 'prefer',
                'prediction_type': prediction.prediction_type,
                'context': prediction.context,
                'reason': f'High accuracy ({accuracy:.2f})',
                'learned_at': datetime.now().isoformat()
            }
            self.learned_rules[agent_id].append(rule)
            
            logger.info(
                f"[LearningSystem] 📚 {agent_id} learned to prefer: "
                f"{prediction.prediction_type} in context {prediction.context}"
            )
    
    def get_agent_stats(self, agent_id: str) -> Optional[LearningStats]:
        """Get learning statistics for an agent"""
        return self.stats_by_agent.get(agent_id)
    
    def get_all_stats(self) -> Dict[str, LearningStats]:
        """Get learning statistics for all agents"""
        return {
            agent_id: stats.to_dict()
            for agent_id, stats in self.stats_by_agent.items()
        }
    
    def get_learned_rules(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get adaptation rules learned by agent"""
        return self.learned_rules.get(agent_id, [])
    
    def should_adjust_confidence(
        self,
        agent_id: str,
        prediction_type: str
    ) -> Tuple[bool, float]:
        """
        Check if agent should adjust confidence for this prediction type.
        
        Returns:
            (should_adjust, suggested_confidence_modifier)
        
        Example:
            adjust, modifier = learning.should_adjust_confidence(
                'strategist',
                'score_change'
            )
            if adjust:
                confidence *= modifier  # Reduce confidence if historically inaccurate
        """
        stats = self.stats_by_agent.get(agent_id)
        if not stats or stats.verified_predictions < 5:
            # Not enough data
            return False, 1.0
        
        # Check accuracy for this prediction type
        type_accuracy = stats.accuracy_by_type.get(prediction_type)
        if type_accuracy is None:
            return False, 1.0
        
        # If accuracy is poor, reduce confidence
        if type_accuracy < 0.5:
            # Poor accuracy - be less confident
            modifier = 0.7
            return True, modifier
        
        elif type_accuracy > 0.8:
            # Great accuracy - can be more confident
            modifier = 1.2
            return True, modifier
        
        return False, 1.0
    
    def get_prediction_history(
        self,
        agent_id: str,
        prediction_type: Optional[str] = None,
        verified_only: bool = False,
        limit: int = 10
    ) -> List[Prediction]:
        """
        Get prediction history for agent.
        
        Args:
            agent_id: Agent ID
            prediction_type: Optional filter by type
            verified_only: Only return verified predictions
            limit: Max number to return
        """
        prediction_ids = self.predictions_by_agent.get(agent_id, [])
        predictions = [
            self.predictions[pid]
            for pid in prediction_ids
            if pid in self.predictions
        ]
        
        # Filter
        if prediction_type:
            predictions = [
                p for p in predictions
                if p.prediction_type == prediction_type
            ]
        
        if verified_only:
            predictions = [p for p in predictions if p.is_verified()]
        
        # Sort by date (newest first)
        predictions.sort(key=lambda p: p.created_at, reverse=True)
        
        return predictions[:limit]


# Global learning system instance
_learning_system: Optional[LearningSystem] = None


def get_learning_system() -> LearningSystem:
    """Get or create global learning system"""
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem()
    return _learning_system


def reset_learning_system():
    """Reset global learning system (for testing)"""
    global _learning_system
    _learning_system = None
